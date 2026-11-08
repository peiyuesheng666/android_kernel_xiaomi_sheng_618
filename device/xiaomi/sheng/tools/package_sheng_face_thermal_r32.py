#!/usr/bin/env python3
"""Seal the reviewed r32 face integration and thermal ownership delta over r31."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from freeze_sheng_batch_inputs import CompiledContexts, erofs_new_nodes
from package_sheng_batch_helpers import (
    erofs_input_keys, merge_parent, packaging_input_path, publish_batch,
    stage_erofs, stage_ext4, tree_descriptor, validate_inputs, validate_packaging_inputs,
)
from package_sheng_color_functions import source_paths
from package_sheng_model_followup import PRODUCT, ROM, parse_image, sha

DEVICE = Path(__file__).resolve().parents[1]
DIAG = Path('/root/sheng-lineage/hardware-diagnostics')
REVIEW = 'docs/r32-face-final-build-review-20261108.json'
PINNED = {
    'system': ('r30', 1005133824, '0f9c8ad6341faae4abaa9c080614d6d879aa62e85e36383086bb0333adfb4dce'),
    'vendor': ('r31', 303517696, '033fdfcc1100e8d504739c43442a6b4e57e73088b938d2f9a9bff9369702217f'),
    'odm': ('r30', 1141067776, 'eecbef1b87f4055f5c35c519d2d1d220b479e0fe6320d970708e277ebba532c0'),
    'vbmeta': ('r31', 8192, 'f6ba37f234fcdacbd36b7837e1d6f6a3ecd6cb147269291548089e626fb9a834'),
    'vbmeta_system': ('r30', 4096, '7f3c4603e9fc7fedd923b074c9086c2d3520d7b375add56bbbb3d32f7a07411c'),
}
SCOPE = {
    'system': {'etc/vintf/compatibility_matrix.device.xml'},
    'vendor': {'lib64/android.hardware.biometrics.common-V2-ndk.so',
               'lib64/android.hardware.biometrics.face-V2-ndk.so',
               'etc/permissions/android.hardware.biometrics.face.xml',
               'etc/selinux/vendor_sepolicy.cil', 'etc/selinux/vendor_file_contexts',
               'etc/selinux/vendor_hwservice_contexts'},
    'odm': {'bin/hw/android.hardware.biometrics.face-aidl-service', 'bin/mifaced@1.0',
            'etc/init/android.hardware.biometrics.face-aidl-service.rc',
            'etc/init/vendor.xiaomi.hardware.miface@1.0-service.rc',
            'etc/vintf/manifest/face-default.xml',
            'etc/vintf/manifest/manifest_vendor.xiaomi.hardware.miface.xml',
            'etc/selinux/precompiled_sepolicy'},
}
NEW_NODES = {
    'system': set(),
    'vendor': {p for p in SCOPE['vendor'] if not p.startswith('etc/selinux/')},
    'odm': SCOPE['odm'] - {'etc/selinux/precompiled_sepolicy'},
}


def bases_for(workspace):
    bases = {p: workspace / f'artifacts/system-hardware-followup-sheng-{rev}/{p}.img'
             for p, (rev, _, _) in PINNED.items()}
    for p, image in bases.items():
        assert image.is_file() and not image.is_symlink()
        assert image.stat().st_size == PINNED[p][1] and sha(image) == PINNED[p][2], p
    return bases


def validate(spec, workspace):
    review = json.loads((DEVICE / REVIEW).read_text())
    for key in ('scoped_configuration_assembly_passed', 'baseline_matrix_byte_reproduced',
                'only_miface_matrix_hal_added', 'complete_live_vintf_compatibility_passed',
                'actual_kernel_config_checked', 'exact_face_context_and_policy_checks_passed',
                'postbuild_public_audit_passed', 'normal_strip_rule_reused',
                'all_runtime_elf_sections_preserved', 'five_stripped_candidate_elf_checks_passed'):
        assert review[key] is True, key
    assert review['full_product_build_passed'] is False
    assert review['normal_product_module_build_passed'] is False
    assert spec['revision'] == 32 and set(spec['partitions']) == set(SCOPE)
    assert spec['baseline_sha256'] == {p: v[2] for p, v in PINNED.items()}
    assert spec['reviews_sha256'] == {REVIEW: sha(DEVICE / REVIEW)}
    for p, stage in spec['partitions'].items():
        assert set(stage['files']) == SCOPE[p] and set(stage['new_nodes']) == NEW_NODES[p]
        validate_inputs(p, stage['files'])
        for relative, value in stage['files'].items():
            assert value['sha256'] == review['reviewed_sha256'][p][relative]
        for relative, node in stage['new_nodes'].items():
            assert node['uid'] == node['gid'] == 0
            assert node['mode'] == (0o755 if relative.startswith('bin/') else 0o644)
            expected_label = ('hal_face_default_exec' if relative.startswith('bin/hw/') else
                              'hal_miface_default_exec' if relative.startswith('bin/') else
                              'vendor_file' if relative.startswith('lib64/') else 'vendor_configs_file')
            assert node['selinux'] == f'u:object_r:{expected_label}:s0', relative
    for relative, digest in review['source_sha256'].items():
        assert sha(DEVICE / relative) == digest, relative
    assert set(source_paths(workspace)) == set(spec['device_inputs'])
    for relative, digest in spec['device_inputs'].items():
        assert sha(DEVICE / relative) == sha(workspace / 'device/xiaomi/sheng' / relative) == digest, relative
    validate_packaging_inputs(spec['partitions'], spec['build_inputs'])
    assert spec['build_inputs']['@sepolicy_file_contexts'] == review['global_contexts_sha256']


def freeze(workspace, path, bases):
    assert not path.exists()
    partitions = {}
    with CompiledContexts(packaging_input_path('@sepolicy_file_contexts').read_bytes()) as labels:
        for p, paths in SCOPE.items():
            files = {r: dict(source=str(PRODUCT / p / r), kind='file',
                            bytes=(PRODUCT / p / r).stat().st_size, sha256=sha(PRODUCT / p / r))
                     for r in sorted(paths)}
            nodes = {} if p == 'system' else erofs_new_nodes(p, bases[p], files, labels)
            for relative, node in nodes.items():
                node['mode'] = 0o755 if relative.startswith('bin/') else 0o644
            partitions[p] = dict(files=files, new_nodes=nodes)
    keys = set().union(*(erofs_input_keys(p) for p in ('vendor', 'odm')))
    spec = dict(revision=32, partitions=partitions,
                baseline_sha256={p: v[2] for p, v in PINNED.items()},
                reviews_sha256={REVIEW: sha(DEVICE / REVIEW)},
                device_inputs={r: sha(DEVICE / r) for r in source_paths(workspace)},
                build_inputs={r: sha(packaging_input_path(r)) for r in sorted(keys)},
                source_commit=subprocess.check_output(['git', '-C', str(workspace), 'rev-parse', 'HEAD'],
                                                      text=True).strip())
    validate(spec, workspace)
    with path.open('x') as stream:
        stream.write(json.dumps(spec, indent=2) + '\n')
    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--spec', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--freeze-only', action='store_true')
    mode.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    assert __debug__ and DEVICE == ROM / 'device/xiaomi/sheng'
    workspace = args.workspace.resolve(strict=True)
    bases = bases_for(workspace)
    spec = freeze(workspace, args.spec, bases) if args.freeze_only else json.loads(args.spec.read_text())
    validate(spec, workspace)
    digest = sha(args.spec)
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    for p in SCOPE:
        parent = 'vbmeta_system' if p == 'system' else 'vbmeta'
        _, _, _, tree = tree_descriptor(avb, avbtool, bases[p], p)
        _, _, descriptors, _ = parse_image(avb, avbtool, bases[parent])
        matches = [d for d in descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)
                   and d.partition_name == p]
        assert len(matches) == 1 and matches[0].encode() == tree.encode(), p
    if args.freeze_only or args.validate_only:
        print(json.dumps(dict(revision=32, validation_passed=True, spec_sha256=digest)))
        return
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r32'
    assert not destination.exists() and shutil.disk_usage(DIAG).free > 20 * 1024**3
    work = Path(tempfile.mkdtemp(prefix='r32-packaging-', dir=DIAG))
    outputs, trees, reports = {}, {}, {}
    for p, stage in spec['partitions'].items():
        print('Staging and independently reading back ' + p, flush=True)
        arguments = p, bases[p], stage['files'], stage['new_nodes'], work, avb, avbtool
        if p == 'system':
            # No APK is added or replaced in this exact system scope.
            image, tree, report = stage_ext4(*arguments, platform_certificate=[])
        else:
            image, tree, report = stage_erofs(*arguments)
        prefix = 'system/' if p == 'system' else ''
        assert set(report['changed_files']) == {prefix + r for r in SCOPE[p]}
        assert report['metadata_preserved']
        outputs[p], trees[p], reports[p] = image, tree, report
    for parent, children, algorithm in (
        ('vbmeta', ('vendor', 'odm'), 'SHA256_RSA4096'),
        ('vbmeta_system', ('system',), 'SHA256_RSA2048'),
    ):
        outputs[parent] = work / (parent + '.img')
        merge_parent(avb, avbtool, bases[parent], [trees[p] for p in children], outputs[parent], algorithm, work)
        _, header, _, _ = parse_image(avb, avbtool, outputs[parent])
        handler = avbtool.ImageHandler(str(outputs[parent]), read_only=True)
        try:
            blob = avb._load_vbmeta_blob(handler)
        finally:
            handler._image.close()
        assert avbtool.verify_vbmeta_signature(header, blob), parent
    validate(spec, workspace)
    bases_for(workspace)
    assert sha(args.spec) == digest and set(outputs) == set(PINNED)
    evidence = workspace / 'artifacts' / ('r32-build-evidence-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    evidence.mkdir()
    for p in work.iterdir():
        if p.is_file() and p.suffix in ('.log', '.txt', '.bin'):
            shutil.copyfile(p, evidence / p.name)
    publish_batch(destination, outputs, dict(revision=32, frozen_spec=spec, spec_sha256=digest,
        baseline_sha256={p: v[2] for p, v in PINNED.items()}, partition_reports=reports,
        exact_baselines_verified=True, all_filesystem_stages_verified=True,
        both_parent_chains_verified=True, both_parent_signatures_verified=True,
        other_avb_descriptors_unchanged=True, original_systemui_required=True,
        system_ext_and_vendor_dlkm_unchanged=True, full_product_build_passed=False,
        persistent_build_evidence_dir=str(evidence), temporary_work_on_tmpfs=False,
        hardware_boot_tested=False, runtime_verified=False))
    assert work.resolve().parent == DIAG and work.name.startswith('r32-packaging-') and not work.is_symlink()
    shutil.rmtree(work)
    print(destination)


if __name__ == '__main__':
    main()
