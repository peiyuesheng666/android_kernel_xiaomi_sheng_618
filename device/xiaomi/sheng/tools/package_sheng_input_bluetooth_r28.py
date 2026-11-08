#!/usr/bin/env python3
"""Build and seal two stylus IDC files and the platform Bluetooth default."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from package_sheng_batch_helpers import (
    erofs_input_keys, merge_parent, packaging_input_path, publish_batch,
    stage_erofs, stage_ext4, tree_descriptor, validate_inputs, validate_packaging_inputs,
)
from package_sheng_color_functions import source_paths
from package_sheng_location_followup import debugfs
from package_sheng_model_followup import HOST, PRODUCT, ROM, parse_image, run, sha
from package_sheng_overlay_followup import complete_metadata

DEVICE = Path(__file__).resolve().parents[1]
ASSEMBLY = Path('/root/sheng-lineage/hardware-diagnostics/r28-config-assembly-attempt4')
REVIEW = 'docs/r28-config-build-review-20261108.json'
AUTO = b'bluetooth.auto_connect_profiles.enabled=true\n'
PENS = ('NVTCapacitivePenM80p.idc', 'NVTCapacitivePenP81c.idc')
SCOPE = {'vendor': {'build.prop', *(f'usr/idc/{p}' for p in PENS)}, 'system_ext': {'etc/build.prop'}}
PINNED = {
    'vendor': ('r26', 303517696, 'f5af272548b0182939c631692a05ca322dfe38aceed103614ca3865145e81528'),
    'system_ext': ('r22', 572813312, '82006f12228ebda0a521a96f8373c48bb52edb981a790830304f8ea50aa60419'),
    'vbmeta': ('r27', 8192, 'ac7f76375e529b428de41c189532190fbbeb48a91909c7cfca292caa6fa0ba18'),
    'vbmeta_system': ('r22', 4096, '3fe3413cc7fe8786372606ebfe7f9470e41bbf34b1dbcb5db7397540d9afc26a'),
}


def bases_for(workspace):
    bases = {p: workspace / f'artifacts/system-hardware-followup-sheng-{r}/{p}.img'
             for p, (r, _, _) in PINNED.items()}
    for p, image in bases.items():
        assert image.is_file() and not image.is_symlink()
        assert image.stat().st_size == PINNED[p][1] and sha(image) == PINNED[p][2], p
    return bases


def property_delta():
    old_vendor = (ASSEMBLY / 'vendor-original.prop').read_bytes()
    old_ext = (ASSEMBLY / 'system_ext-original.prop').read_bytes()
    assert old_vendor.count(AUTO) == 1 and AUTO.split(b'=')[0] not in old_ext
    assert AUTO not in (DEVICE / 'properties/vendor.prop').read_bytes()
    assert (DEVICE / 'properties/system_ext.prop').read_bytes().count(AUTO) == 1
    return {'vendor': old_vendor.replace(AUTO, b''), 'system_ext': old_ext + b'\n' + AUTO}


def prepare(workspace, bases):
    ASSEMBLY.mkdir(parents=True, exist_ok=False)
    pre = Path('/root/sheng-lineage/hardware-diagnostics/r28-prebuild-audit-20261108.json')
    audit = json.loads(pre.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert len(audit['repositories']) == 21 and all(r['fetch']['returncode'] == 0 for r in audit['repositories'])
    old_vendor = json.loads((workspace / 'artifacts/system-hardware-followup-sheng-r26/build-result.json').read_text())[
        'frozen_spec']['partitions']['vendor']['files']['build.prop']['sha256']
    vendor_prop = PRODUCT / 'vendor/build.prop'
    assert sha(vendor_prop) == old_vendor
    shutil.copyfile(vendor_prop, ASSEMBLY / 'vendor-original.prop')
    debugfs(bases['system_ext'], f'dump /etc/build.prop {ASSEMBLY}/system_ext-original.prop')
    assert (PRODUCT / 'system_ext/etc/build.prop').read_bytes() == (ASSEMBLY / 'system_ext-original.prop').read_bytes()
    validator = ROM / 'out/soong/.intermediates/frameworks/base/tools/validatekeymaps/validatekeymaps/linux_glibc_x86_64/validatekeymaps'
    command = [validator, *(DEVICE / 'configs/idc' / p for p in (*PENS, 'NVTCapacitiveTouchScreen.idc'))]
    validator_environment = dict(os.environ, LD_LIBRARY_PATH=str(HOST.parent / 'lib64'))
    result = subprocess.run(list(map(str, command)), env=validator_environment,
                            capture_output=True, text=True)
    (ASSEMBLY / 'platform-idc-validator.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0
    script = ROM / 'build/make/tools/post_process_props.py'
    sys.path[:0] = [str(script.parent), str(ROM / 'build/soong/scripts')]
    module_spec = importlib.util.spec_from_file_location('sheng_property_validation', script)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    for p, data in property_delta().items():
        target = PRODUCT / p / ('build.prop' if p == 'vendor' else 'etc/build.prop')
        check = ASSEMBLY / p / 'build.prop'
        check.parent.mkdir()
        check.write_bytes(data)
        props = module.PropList(str(check))
        assert module.override_optional_props(props, False) and module.validate_grf_props(props) and module.validate(props)
        assert not any(prop.is_optional() for prop in props.get_all_props())
        # This is scoped configuration assembly, retaining every unrelated byte.
        target.write_bytes(data)
    for name in PENS:
        target = PRODUCT / 'vendor/usr/idc' / name
        assert target.parent.is_dir() and not target.is_symlink() and not target.exists()
        shutil.copyfile(DEVICE / 'configs/idc' / name, target)
    review = dict(revision=28,configuration_assembly_passed=True,platform_idc_parser_passed=True,
        platform_build_property_validation_passed=True,full_product_build_passed=False,
        prebuild_public_audit_sha256=sha(pre),prebuild_public_repositories=21,
        input_validator_sha256=sha(validator),input_validator_command=list(map(str,command)),
        input_validator_library_path=str(HOST.parent / 'lib64'),
        input_validator_libraries_sha256={n:sha(HOST.parent/'lib64'/n) for n in ('libvintf.so','libc++.so')},
        input_validator_log_sha256=sha(ASSEMBLY / 'platform-idc-validator.log'),
        property_validation_source_sha256=sha(script),
        original_prop_sha256={p:sha(ASSEMBLY / (p+'-original.prop')) for p in ('vendor','system_ext')},
        compiled_files_sha256={p:{r:sha(PRODUCT/p/r) for r in paths} for p,paths in SCOPE.items()},
        installed=False,runtime_verified=False,headset_reconnect_tested=False,stylus_physical_tested=False,
        lhdc_v5_fixed=False,systemui_changed=False)
    path = DEVICE / REVIEW
    assert not path.exists()
    path.write_text(json.dumps(review,indent=2)+'\n')
    print(path)


def validate(spec, workspace):
    review = json.loads((DEVICE / REVIEW).read_text())
    assert review['configuration_assembly_passed'] and review['platform_idc_parser_passed']
    assert review['platform_build_property_validation_passed']
    assert review.get('postbuild_public_audit_passed') is True
    assert spec['revision'] == 28 and set(spec['partitions']) == set(SCOPE)
    assert spec['baseline_sha256'] == {p:v[2] for p,v in PINNED.items()}
    assert spec['reviews_sha256'] == {REVIEW:sha(DEVICE / REVIEW)}
    for p, entry in spec['partitions'].items():
        assert set(entry['files']) == SCOPE[p]
        assert set(entry['new_nodes']) == ({f'usr/idc/{n}' for n in PENS} if p == 'vendor' else set())
        validate_inputs(p,entry['files'])
        for r, value in entry['files'].items(): assert value['sha256'] == review['compiled_files_sha256'][p][r]
    for p,data in property_delta().items():
        assert (PRODUCT / p / ('build.prop' if p == 'vendor' else 'etc/build.prop')).read_bytes() == data
        assert sha(ASSEMBLY / (p+'-original.prop')) == review['original_prop_sha256'][p]
    assert set(source_paths(workspace)) == set(spec['device_inputs'])
    for r,digest in spec['device_inputs'].items():
        assert sha(DEVICE/r) == sha(workspace/'device/xiaomi/sheng'/r) == digest,r
    validate_packaging_inputs(spec['partitions'],spec['build_inputs'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--spec',type=Path,required=True)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--freeze-only',action='store_true')
    parser.add_argument('--validate-only',action='store_true')
    args=parser.parse_args()
    assert __debug__ and DEVICE.resolve() == ROM/'device/xiaomi/sheng'
    workspace=args.workspace.resolve(strict=True)
    bases=bases_for(workspace)
    if args.prepare_only:
        prepare(workspace,bases)
        return
    if args.freeze_only:
        assert not args.spec.exists()
        metadata,_=complete_metadata(bases['vendor'])
        sample=metadata['/usr/idc/NVTCapacitiveTouchScreen.idc']
        node={k:sample[k] for k in ('uid','gid','mode','mtime_ns')}
        node['selinux']=bytes.fromhex(sample['xattrs']['6:selinux']).rstrip(b'\0').decode()
        partitions={}
        for p,paths in SCOPE.items():
            files={r:dict(source=str(PRODUCT/p/r),kind='file',bytes=(PRODUCT/p/r).stat().st_size,sha256=sha(PRODUCT/p/r)) for r in sorted(paths)}
            for name in PENS:
                if p=='vendor': files[f'usr/idc/{name}']['device_source']=f'configs/idc/{name}'
            partitions[p]=dict(files=files,new_nodes={f'usr/idc/{n}':node for n in PENS} if p=='vendor' else {})
        spec=dict(revision=28,partitions=partitions,baseline_sha256={p:v[2] for p,v in PINNED.items()},
            device_inputs={r:sha(DEVICE/r) for r in source_paths(workspace)},
            build_inputs={r:sha(packaging_input_path(r)) for r in sorted(erofs_input_keys('vendor'))},
            reviews_sha256={REVIEW:sha(DEVICE/REVIEW)},
            source_commit=subprocess.check_output(['git','-C',str(workspace),'rev-parse','HEAD'],text=True).strip())
        validate(spec,workspace)
        with args.spec.open('x') as stream: stream.write(json.dumps(spec,indent=2)+'\n')
    else: spec=json.loads(args.spec.read_text())
    validate(spec,workspace)
    sys.path.insert(0,str(ROM/'external/avb'))
    import avbtool
    avb=avbtool.Avb()
    for child,parent in (('vendor','vbmeta'),('system_ext','vbmeta_system')):
        _,_,_,tree=tree_descriptor(avb,avbtool,bases[child],child)
        _,_,descriptors,_=parse_image(avb,avbtool,bases[parent])
        matching=[d for d in descriptors if isinstance(d,avbtool.AvbHashtreeDescriptor) and d.partition_name==child]
        assert len(matching)==1 and matching[0].encode()==tree.encode()
    if args.freeze_only or args.validate_only:
        print(json.dumps(dict(revision=28,validation_passed=True,spec_sha256=sha(args.spec))))
        return
    destination=workspace/'artifacts/system-hardware-followup-sheng-r28'
    assert not destination.exists() and shutil.disk_usage('/dev/shm').free>6*1024**3
    work=Path(tempfile.mkdtemp(prefix='sheng-r28-',dir='/dev/shm'))
    outputs,trees,reports={},{},{}
    for p in ('vendor','system_ext'):
        print('Staging and independently reading back '+p,flush=True)
        stage=spec['partitions'][p]
        if p=='vendor': result=stage_erofs(p,bases[p],stage['files'],stage['new_nodes'],work,avb,avbtool)
        else: result=stage_ext4(p,bases[p],stage['files'],stage['new_nodes'],work,avb,avbtool,set())
        outputs[p],trees[p],reports[p]=result
        assert set(reports[p]['changed_files'])==SCOPE[p] and reports[p]['metadata_preserved']
        if p=='vendor':
            assert reports[p]['baseline_entries']['build.prop']==('file',sha(ASSEMBLY/'vendor-original.prop'))
            assert all(reports[p]['baseline_entries'][f'usr/idc/{n}'] is None for n in PENS)
    assert sha(work/'system_ext-after/priv-app/SystemUI/SystemUI.apk')=='33017b0d59e28da5db3e089a98f49601de508228a012392ee2d04c82cda3ccb1'
    for child,parent,algorithm in (('vendor','vbmeta','SHA256_RSA4096'),('system_ext','vbmeta_system','SHA256_RSA2048')):
        outputs[parent]=work/(parent+'.img')
        merge_parent(avb,avbtool,bases[parent],[trees[child]],outputs[parent],algorithm,work)
        _,header,_,_=parse_image(avb,avbtool,outputs[parent])
        handler=avbtool.ImageHandler(str(outputs[parent]),read_only=True)
        try: blob=avb._load_vbmeta_blob(handler)
        finally: handler._image.close()
        assert avbtool.verify_vbmeta_signature(header,blob)
    validate(spec,workspace)
    bases_for(workspace)
    evidence=workspace/'artifacts'/('r28-build-evidence-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    evidence.mkdir()
    for p in work.iterdir():
        if p.is_file() and p.suffix in ('.log','.txt','.bin'): shutil.copyfile(p,evidence/p.name)
    publish_batch(destination,outputs,dict(revision=28,frozen_spec=spec,spec_sha256=sha(args.spec),
        baseline_sha256={p:v[2] for p,v in PINNED.items()},partition_reports=reports,
        exact_baselines_verified=True,all_filesystem_stages_verified=True,
        root_signature_verified=True,root_other_descriptors_unchanged=True,
        system_chain_signature_verified=True,system_chain_other_descriptors_unchanged=True,
        original_systemui_required=True,persistent_build_evidence_dir=str(evidence),temporary_work_on_tmpfs=True,
        hardware_boot_tested=False,runtime_verified=False))
    assert work.parent==Path('/dev/shm') and work.name.startswith('sheng-r28-')
    shutil.rmtree(work)
    print(destination)


if __name__=='__main__': main()
