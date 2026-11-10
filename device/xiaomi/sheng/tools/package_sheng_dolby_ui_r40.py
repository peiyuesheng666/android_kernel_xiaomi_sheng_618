#!/usr/bin/env python3
"""Replace only the reviewed Dolby APK over verified r39 system_ext and AVB."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from package_sheng_batch_helpers import certificates, debugfs, merge_parent, publish_batch, stage_ext4
from package_sheng_model_followup import HOST, PRODUCT, ROM, sha

PINNED = {
    'system_ext': '851c37194a1bb23f79c319f29688c3b1332307e12084424df5d0989b2b8d65b0',
    'vbmeta_system': '6616543aadf5e3da118b5c1efa6c5b766e0d5bb90c4d4340e13e24859bbb5854',
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--build-review',type=Path,required=True)
    parser.add_argument('--post-audit',type=Path,required=True)
    parser.add_argument('--revision',type=int,choices=(40,41),default=40)
    args=parser.parse_args()
    assert __debug__
    workspace=args.workspace.resolve(strict=True)
    build=json.loads(args.build_review.read_text()); audit=json.loads(args.post_audit.read_text())
    assert build['scoped_build_passed'] and build['api1_bootstrap_compile_passed'] and build['v1_signature_verified']
    if args.revision==41:assert build.get('normal_module_build_passed',False)
    assert not build['launcher_entry_present'] and build['settings_entry_present'] and not build['systemui_changed']
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert datetime.now(timezone.utc).timestamp()-datetime.fromisoformat(audit['date_utc']).timestamp()<7200
    for path,digest in build['sources_sha256'].items():assert sha(Path(path))==digest,path
    r38=json.loads((workspace/'reports/device/r38-restore-20261110/restore-manifest.json').read_text())
    chain_inputs={e['partition']:workspace/e['path'] for e in r38['files']}
    for revision in range(39,args.revision):
        parent_dir=workspace/f'artifacts/system-hardware-followup-sheng-r{revision}'
        parent=json.loads((parent_dir/'build-result.json').read_text())
        assert parent['revision']==revision and parent['complete_avb_chain_verified'] and parent['all_filesystem_stages_verified']
        for entry in parent['files']:
            path=parent_dir/entry['name']
            assert path.stat().st_size==entry['bytes'] and sha(path)==entry['sha256']
            chain_inputs[entry['partition']]=path
        if revision==39:
            assert {p:sha(chain_inputs[p]) for p in PINNED}==PINNED
    bases={p:chain_inputs[p] for p in PINNED}
    baseline_sha256={p:sha(v) for p,v in bases.items()}
    assert build['revision']==args.revision
    destination=workspace/f'artifacts/system-hardware-followup-sheng-r{args.revision}'
    assert not destination.exists() and shutil.disk_usage('/dev/shm').free>3*1024**3
    work=Path(tempfile.mkdtemp(prefix=f'sheng-r{args.revision}-',dir='/dev/shm'))
    relative='priv-app/ShengDolby/ShengDolby.apk'
    source=Path(build['payload']['path']); installed=PRODUCT/'system_ext'/relative
    assert source.stat().st_size==build['payload']['bytes'] and sha(source)==build['payload']['sha256']
    shutil.copyfile(installed,work/'installed-before-packaging-ShengDolby.apk')
    entries={relative:dict(source=str(source),kind='file',bytes=source.stat().st_size,sha256=sha(source))}
    sys.path.insert(0,str(ROM/'external/avb'))
    import avbtool
    avb=avbtool.Avb()
    reference=work/'platform-reference.apk'
    debugfs(bases['system_ext'],f'dump /priv-app/SystemUI/SystemUI.apk {reference}')
    assert sha(reference)=='33017b0d59e28da5db3e089a98f49601de508228a012392ee2d04c82cda3ccb1'
    image,tree,report=stage_ext4('system_ext',bases['system_ext'],entries,{},work,avb,avbtool,certificates(reference))
    assert report['changed_files']==[relative] and report['metadata_preserved'] and not report['created_nodes']
    outputs=dict(system_ext=image,vbmeta_system=work/'vbmeta_system.img')
    merge_parent(avb,avbtool,bases['vbmeta_system'],[tree],outputs['vbmeta_system'],'SHA256_RSA2048',work)
    chain=work/'complete-chain'; chain.mkdir()
    for p,path in chain_inputs.items():(chain/(p+'.img')).symlink_to(outputs.get(p,path).resolve())
    result=subprocess.run([HOST/'avbtool','verify_image','--image',chain/'vbmeta.img','--follow_chain_partitions'],
                          capture_output=True,text=True)
    (work/'complete-chain.avb.txt').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    for path,digest in build['sources_sha256'].items():assert sha(Path(path))==digest
    assert {p:sha(v) for p,v in bases.items()}==baseline_sha256
    evidence=workspace/'reports/device/20261110-resume/dolby' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-package')
    evidence.mkdir(parents=True)
    for path in work.iterdir():
        if path.is_file() and path.suffix in ('.log','.txt','.json'):shutil.copyfile(path,evidence/path.name)
    publish_batch(destination,outputs,dict(revision=args.revision,baseline_sha256=baseline_sha256,
        build_review_sha256=sha(args.build_review),post_audit_sha256=sha(args.post_audit),
        source_commit=subprocess.check_output(['git','-C',workspace,'rev-parse','HEAD'],text=True).strip(),
        entries=entries,partition_reports=dict(system_ext=report),all_filesystem_stages_verified=True,
        complete_avb_chain_verified=True,original_systemui_unchanged=True,root_vbmeta_unchanged=True,
        normal_module_build_passed=build.get('normal_module_build_passed',False),
        full_product_build_passed=False,api1_runtime_tested=False,hardware_boot_tested=False,
        persistent_build_evidence_dir=str(evidence),work_dir=str(work)))
    print(destination,flush=True)


if __name__=='__main__':main()
