#!/usr/bin/env python3
"""Freeze and package the r16 white-balance delta against the installed r15 chain."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from package_sheng_batch_helpers import (
    erofs_input_keys, merge_parent, packaging_input_path, publish_batch,
    relative_path, stage_erofs, tree_descriptor, validate_inputs,
    validate_packaging_inputs,
)
from package_sheng_model_followup import PRODUCT, ROM, parse_image, sha

DEVICE = Path(__file__).resolve().parents[1]
FILTERED_SENSOR_SHA256 = '20739ca0b279d8570d081a549788db5e5d44fa2a84e330eb58317cd4c99a19ec'
SCOPE = {
    'odm': {'overlay/FrameworkResOverlaySheng.apk'},
    'vendor': {'bin/hw/android.hardware.sensors-service.sheng-multihal'},
}
PINNED = {
    'odm': ('r15', 1141067776, '34f43bd4c28e56da32536e78ce400cfeeb549640d03282556ddc41d999637bf5'),
    'vendor': ('r15', 303517696, '5fe250a2be26a15b45a2e843121b1001323c5faa4cbd1dc42ef06c2f5a76875f'),
    'vbmeta': ('r15', 8192, 'd13bd3783dc9d3d10c3b3c16cfca78bead132ed22a36ac7d97870f1371ef8b57'),
    'system': ('r13', 1005133824, '0551a74f4f995793665a485d10caacffb22ccd8fdaffb78d7811d17c658b3ac1'),
    'vbmeta_system': ('r13', 4096, 'a947be896074811b496f42cf3759def63f808518869f56ed6c67c608622cd165'),
    'system_ext': ('r9', None, '7a4e2a739f9cbc3a9713113e40f8a181dde34875c1ef0abee5e53411de58c573'),
}


def source_paths(workspace):
    output = subprocess.run(['git', '-C', str(workspace), 'ls-files', '-z', '--',
                             'device/xiaomi/sheng'], check=True, capture_output=True).stdout
    prefix = 'device/xiaomi/sheng/'
    paths = [path.decode().removeprefix(prefix) for path in output.split(b'\0') if path]
    return sorted(path for path in paths if not path.startswith('docs/'))


def validate(spec, workspace):
    assert set(spec) == {'revision', 'partitions', 'device_inputs', 'build_inputs', 'source_commit'}
    assert spec['revision'] == 16 and set(spec['partitions']) == set(SCOPE)
    assert spec['partitions']['vendor']['bin/hw/android.hardware.sensors-service.sheng-multihal']['sha256'] == FILTERED_SENSOR_SHA256, \
        'Only the compiled invalid-CCT sensor service may be packaged as r16'
    for partition, files in spec['partitions'].items():
        assert set(files) == SCOPE[partition], 'Unexpected display batch scope'
        validate_inputs(partition, files)
    validate_packaging_inputs(spec['partitions'], spec['build_inputs'])
    assert set(source_paths(workspace)) == set(spec['device_inputs']), 'Tracked source list changed'
    for relative, digest in spec['device_inputs'].items():
        relative_path(relative)
        local = workspace / 'device/xiaomi/sheng' / relative
        source = DEVICE / relative
        assert local.is_file() and source.is_file() and not source.is_symlink()
        assert sha(local) == sha(source) == digest, f'Device source changed: {relative}'


def freeze(workspace, destination):
    assert not destination.exists(), 'Never replace a frozen spec'
    files = {}
    for partition, paths in SCOPE.items():
        files[partition] = {}
        for relative in sorted(paths):
            source = PRODUCT / partition / relative
            files[partition][relative] = dict(source=str(source), bytes=source.stat().st_size,
                                               sha256=sha(source), kind='file')
    inputs = set().union(*(erofs_input_keys(p) for p in SCOPE))
    spec = dict(revision=16, partitions=files,
                device_inputs={p: sha(DEVICE / p) for p in source_paths(workspace)},
                build_inputs={p: sha(packaging_input_path(p)) for p in sorted(inputs)},
                source_commit=subprocess.run(['git', '-C', str(workspace), 'rev-parse', 'HEAD'],
                                             check=True, capture_output=True, text=True).stdout.strip())
    validate(spec, workspace)
    with destination.open('x') as stream:
        stream.write(json.dumps(spec, indent=2) + '\n')
    return spec


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--spec', required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--freeze-only', action='store_true')
    mode.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    spec = freeze(workspace, args.spec) if args.freeze_only else json.loads(args.spec.read_text())
    spec_hash = sha(args.spec)
    validate(spec, workspace)
    bases = {p: workspace / f'artifacts/system-hardware-followup-sheng-{release}/{p}.img'
             for p, (release, _, _) in PINNED.items()}
    for partition, image in bases.items():
        _, size, digest = PINNED[partition]
        assert (size is None or image.stat().st_size == size) and sha(image) == digest, partition
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    _, _, parent_descriptors, _ = parse_image(avb, avbtool, bases['vbmeta'])
    for partition in SCOPE:
        _, _, _, descriptor = tree_descriptor(avb, avbtool, bases[partition], partition)
        matches = [d for d in parent_descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)
                   and d.partition_name == partition]
        assert len(matches) == 1 and matches[0].encode() == descriptor.encode(), partition
    if args.freeze_only or args.validate_only:
        print(json.dumps(dict(revision=16, frozen_spec_sha256=spec_hash, validation_passed=True)))
        return
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r16'
    assert not destination.exists(), 'Never overwrite a published batch'
    work = Path('/root/sheng-lineage/hardware-followup') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-livedisplay-r16')
    work.mkdir(parents=True)
    outputs, descriptors, reports = {}, [], {}
    for partition, files in spec['partitions'].items():
        image, descriptor, report = stage_erofs(partition, bases[partition], files, {}, work, avb, avbtool)
        assert set(report['changed_files']) == SCOPE[partition], partition
        outputs[partition], reports[partition] = image, report
        descriptors.append(descriptor)
    outputs['vbmeta'] = work / 'vbmeta.img'
    merge_parent(avb, avbtool, bases['vbmeta'], descriptors, outputs['vbmeta'], 'SHA256_RSA4096', work)
    validate(spec, workspace)
    assert sha(args.spec) == spec_hash, 'Frozen spec changed'
    for partition, image in bases.items():
        assert sha(image) == PINNED[partition][2], 'Baseline changed'
    report = dict(revision=16, frozen_spec=spec, frozen_spec_sha256=spec_hash,
                  baseline_sha256={p: value[2] for p, value in PINNED.items()},
                  partition_reports=reports, work_dir=str(work),
                  exact_baselines_verified=True, all_filesystem_stages_verified=True,
                  vbmeta_parent_verified=True, hardware_boot_tested=False, runtime_verified=False)
    publish_batch(destination, outputs, report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
