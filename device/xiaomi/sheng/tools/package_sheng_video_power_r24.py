#!/usr/bin/env python3
"""Freeze/package r24's two video libraries and signed SystemUI APK over r23."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from package_sheng_batch_helpers import (
    certificates, debugfs, erofs_input_keys, merge_parent, packaging_input_path,
    publish_batch, stage_erofs, stage_ext4, tree_descriptor, validate_inputs,
    validate_packaging_inputs,
)
from package_sheng_color_functions import source_paths
from package_sheng_model_followup import PRODUCT, ROM, parse_image, sha

DEVICE = Path(__file__).resolve().parents[1]
REVIEW = 'docs/build-r24-video-power-20261108.json'
PINNED = {
    'vendor': ('r23', 303517696, '49205891b29be48360a717733200a94d8179f4615cf98008b5094fc5e46a481e'),
    'vbmeta': ('r23', 8192, 'c6a46fc8589e5fefb5f84bcc5eb0bae724df03d35c0b016c7ac986e5474804d3'),
    'system_ext': ('r22', 572813312, '82006f12228ebda0a521a96f8373c48bb52edb981a790830304f8ea50aa60419'),
    'vbmeta_system': ('r22', 4096, '3fe3413cc7fe8786372606ebfe7f9470e41bbf34b1dbcb5db7397540d9afc26a'),
    'system': ('r20', 1005133824, '0f9c8ad6341faae4abaa9c080614d6d879aa62e85e36383086bb0333adfb4dce'),
}
SCOPE = {
    'vendor': {'lib64/c2.dolby.hevc.dec.so', 'lib64/c2.dolby.hevc.sec.dec.so'},
    'system_ext': {'priv-app/SystemUI/SystemUI.apk'},
}
INSTALLED_SOURCES = {'priv-app/SystemUI/SystemUI.apk': 'priv-app/ShengSystemUI/SystemUI.apk'}
OUTPUTS = {p: PINNED[p][1] for p in (*SCOPE, 'vbmeta', 'vbmeta_system')}


def bases_for(workspace):
    bases = {p: workspace / f'artifacts/system-hardware-followup-sheng-{release}/{p}.img'
             for p, (release, _, _) in PINNED.items()}
    for p, path in bases.items():
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_size == PINNED[p][1] and sha(path) == PINNED[p][2], p
    return bases


def validate(spec, workspace):
    review = json.loads((DEVICE / REVIEW).read_text())
    for key in ('build_passed', 'helper_tests_passed', 'upstream_audit_passed',
                'geometry_tests_passed', 'apk_transform_verified'):
        assert review[key] is True, key
    assert set(spec) == {'revision', 'partitions', 'device_inputs', 'build_inputs',
                         'source_commit', 'expected_outputs', 'build_review_sha256', 'installed_sources'}
    assert spec['revision'] == 24 and spec['expected_outputs'] == OUTPUTS
    assert spec['installed_sources'] == {'system_ext': INSTALLED_SOURCES}
    assert spec['build_review_sha256'] == sha(DEVICE / REVIEW)
    assert set(spec['partitions']) == set(SCOPE) == set(review['reviewed_sha256'])
    for p, stage in spec['partitions'].items():
        assert set(stage) == {'files', 'new_nodes'} and not stage['new_nodes']
        assert set(stage['files']) == SCOPE[p] == set(review['reviewed_sha256'][p])
        for relative, entry in stage['files'].items():
            assert entry['kind'] == 'file'
            assert entry['sha256'] == review['reviewed_sha256'][p][relative]
        validate_inputs(p, stage['files'], installed_sources=spec['installed_sources'].get(p))
    validate_packaging_inputs(spec['partitions'], spec['build_inputs'])
    assert set(source_paths(workspace)) == set(spec['device_inputs'])
    for relative, digest in spec['device_inputs'].items():
        assert sha(DEVICE / relative) == sha(workspace / 'device/xiaomi/sheng' / relative) == digest, relative
    for relative, digest in review['source_sha256'].items():
        assert sha(DEVICE / relative) == digest, relative


def freeze(workspace, destination):
    assert not destination.exists(), 'Never overwrite frozen inputs'
    partitions = {}
    for p, paths in SCOPE.items():
        files = {}
        for relative in sorted(paths):
            installed = INSTALLED_SOURCES.get(relative, relative) if p == 'system_ext' else relative
            source = PRODUCT / p / installed
            files[relative] = dict(source=str(source), kind='file', bytes=source.stat().st_size,
                                   sha256=sha(source))
        partitions[p] = dict(files=files, new_nodes={})
    keys = erofs_input_keys('vendor') | {'obj/PACKAGING/system_ext_intermediates/system_ext_image_info.txt'}
    spec = dict(revision=24, partitions=partitions, installed_sources={'system_ext': INSTALLED_SOURCES},
                expected_outputs=OUTPUTS, build_review_sha256=sha(DEVICE / REVIEW),
                device_inputs={p: sha(DEVICE / p) for p in source_paths(workspace)},
                build_inputs={p: sha(packaging_input_path(p)) for p in sorted(keys)},
                source_commit=subprocess.check_output(['git', '-C', str(workspace), 'rev-parse', 'HEAD'], text=True).strip())
    validate(spec, workspace)
    with destination.open('x') as stream:
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
    assert __debug__ and DEVICE.resolve() == ROM / 'device/xiaomi/sheng'
    workspace = args.workspace.resolve(strict=True)
    bases = bases_for(workspace)
    spec = freeze(workspace, args.spec) if args.freeze_only else json.loads(args.spec.read_text())
    validate(spec, workspace)
    digest = sha(args.spec)
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    for p in SCOPE:
        _, _, _, tree = tree_descriptor(avb, avbtool, bases[p], p)
        parent = bases['vbmeta' if p == 'vendor' else 'vbmeta_system']
        _, _, descriptors, _ = parse_image(avb, avbtool, parent)
        selected = [d for d in descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)
                    and d.partition_name == p]
        assert len(selected) == 1 and selected[0].encode() == tree.encode()
    if args.freeze_only or args.validate_only:
        print(json.dumps(dict(revision=24, spec_sha256=digest, validation_passed=True)))
        return
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r24'
    assert not destination.exists(), 'Never overwrite a published batch'
    work = Path('/root/sheng-lineage/hardware-followup') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-video-power-r24')
    work.mkdir(parents=True)
    reference = work / 'platform-reference.apk'
    debugfs(bases['system'], f'dump /system/framework/framework-res.apk {reference}')
    platform = certificates(reference)
    outputs, trees, reports = {}, {}, {}
    for p, stage in spec['partitions'].items():
        arguments = p, bases[p], stage['files'], {}, work, avb, avbtool
        image, tree, report = (stage_erofs(*arguments) if p == 'vendor' else
            stage_ext4(*arguments, platform, installed_sources=INSTALLED_SOURCES))
        assert set(report['changed_files']) == SCOPE[p] and not report.get('created_nodes')
        outputs[p], trees[p], reports[p] = image, tree, report
    for parent, partition, algorithm in (
        ('vbmeta', 'vendor', 'SHA256_RSA4096'),
        ('vbmeta_system', 'system_ext', 'SHA256_RSA2048'),
    ):
        outputs[parent] = work / (parent + '.img')
        merge_parent(avb, avbtool, bases[parent], [trees[partition]], outputs[parent], algorithm, work)
    validate(spec, workspace)
    assert sha(args.spec) == digest and set(outputs) == set(OUTPUTS)
    bases_for(workspace)
    report = dict(revision=24, frozen_spec=spec, spec_sha256=digest,
                  baseline_sha256={p: v[2] for p, v in PINNED.items()},
                  partition_reports=reports, work_dir=str(work), platform_certificate=platform,
                  exact_baselines_verified=True, all_filesystem_stages_verified=True,
                  both_parent_chains_verified=True, hardware_boot_tested=False, runtime_verified=False)
    publish_batch(destination, outputs, report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
