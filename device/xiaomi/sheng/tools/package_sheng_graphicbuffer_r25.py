#!/usr/bin/env python3
"""Freeze/package seven reviewed GraphicBuffer allocation repairs over r24."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from package_sheng_batch_helpers import (
    erofs_input_keys, merge_parent, packaging_input_path, publish_batch,
    stage_erofs, tree_descriptor, validate_inputs, validate_packaging_inputs,
)
from package_sheng_color_functions import source_paths
from package_sheng_model_followup import PRODUCT, ROM, parse_image, sha

DEVICE = Path(__file__).resolve().parents[1]
REVIEW = 'docs/build-r25-graphicbuffer-20261108.json'
PINNED = {
    'odm': ('r22', 1141067776, 'c315f3e80f292909740d3e052102dcabb36b3f3bcaa817918f9dbc92630ce651'),
    'vendor': ('r24', 303517696, '4aa0518217ad9521d044b7408348039eb88457fa855bc3544cb499fea0299026'),
    'vbmeta': ('r24', 8192, '883ba3ee6d22460c8a14f5a0eb04aabb4544d1d48d2386de52715b16ca7a9493'),
}
SCOPE = {
    'odm': {'lib64/hw/camera.xiaomi.so', 'lib64/libcom.xiaomi.grallocutils.so',
            'lib64/libcom.xiaomi.mawutils.so', 'lib64/libmis_plugin_vidhance.so'},
    'vendor': {'lib64/c2.dolby.hevc.dec.so', 'lib64/c2.dolby.hevc.enc.so',
               'lib64/c2.dolby.hevc.sec.dec.so'},
}
OUTPUTS = {partition: entry[1] for partition, entry in PINNED.items()}
PROVIDERS = {
    'lib64/libui.so': '5d6f48b97bbcbf79ce805f96e7d7043597154dbd8c615a8a4dfcaf8b916bf3f1',
    'lib64/libgui_vendor.so': '0b082826f4787ea3332e282e7c9de877c4e7384d388bdb68fdb7fbcdf0b231c3',
}


def bases_for(workspace):
    result = {p: workspace / f'artifacts/system-hardware-followup-sheng-{revision}/{p}.img'
              for p, (revision, _, _) in PINNED.items()}
    for p, path in result.items():
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_size == PINNED[p][1] and sha(path) == PINNED[p][2], p
    return result


def validate(spec, workspace):
    review = json.loads((DEVICE / REVIEW).read_text())
    for key in ('build_passed', 'helper_tests_passed', 'upstream_audit_passed',
                'layout_archive_verified', 'allocation_instructions_verified'):
        assert review[key] is True, key
    assert review['allocation_sites'] == 14 and review['malformed_input_checks_passed'] == 5
    assert review['dependency_library_sha256'] == PROVIDERS
    assert set(spec) == {'revision', 'partitions', 'device_inputs', 'build_inputs',
                         'source_commit', 'expected_outputs', 'build_review_sha256'}
    assert spec['revision'] == 25 and spec['expected_outputs'] == OUTPUTS
    assert spec['build_review_sha256'] == sha(DEVICE / REVIEW)
    assert set(spec['partitions']) == set(SCOPE) == set(review['reviewed_sha256'])
    for p, stage in spec['partitions'].items():
        assert set(stage) == {'files', 'new_nodes'} and not stage['new_nodes']
        assert set(stage['files']) == SCOPE[p] == set(review['reviewed_sha256'][p])
        assert set(review['original_sha256'][p]) == SCOPE[p]
        for relative, entry in stage['files'].items():
            assert entry['kind'] == 'file' and entry['sha256'] == review['reviewed_sha256'][p][relative]
        validate_inputs(p, stage['files'])
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
            source = PRODUCT / p / relative
            files[relative] = dict(source=str(source), kind='file', bytes=source.stat().st_size,
                                   sha256=sha(source))
        partitions[p] = dict(files=files, new_nodes={})
    keys = set().union(*(erofs_input_keys(p) for p in SCOPE))
    spec = dict(revision=25, partitions=partitions, expected_outputs=OUTPUTS,
                build_review_sha256=sha(DEVICE / REVIEW),
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
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--freeze-only', action='store_true')
    modes.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    assert __debug__ and DEVICE.resolve() == ROM / 'device/xiaomi/sheng'
    workspace = args.workspace.resolve(strict=True)
    bases = bases_for(workspace)
    spec = freeze(workspace, args.spec) if args.freeze_only else json.loads(args.spec.read_text())
    validate(spec, workspace)
    spec_digest = sha(args.spec)
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    _, _, descriptors, _ = parse_image(avb, avbtool, bases['vbmeta'])
    for p in SCOPE:
        _, _, _, tree = tree_descriptor(avb, avbtool, bases[p], p)
        selected = [d for d in descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)
                    and d.partition_name == p]
        assert len(selected) == 1 and selected[0].encode() == tree.encode()
    if args.freeze_only or args.validate_only:
        print(json.dumps(dict(revision=25, spec_sha256=spec_digest, validation_passed=True)))
        return
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r25'
    assert not destination.exists(), 'Never overwrite a published batch'
    work = Path('/root/sheng-lineage/hardware-followup') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-graphicbuffer-r25')
    work.mkdir(parents=True)
    outputs, trees, reports = {}, {}, {}
    for p, stage in spec['partitions'].items():
        image, tree, report = stage_erofs(p, bases[p], stage['files'], {}, work, avb, avbtool)
        assert set(report['changed_files']) == SCOPE[p] and not report.get('created_nodes')
        review = json.loads((DEVICE / REVIEW).read_text())
        for relative in SCOPE[p]:
            assert report['baseline_entries'][relative] == ('file', review['original_sha256'][p][relative])
        outputs[p], trees[p], reports[p] = image, tree, report
    for relative, dependency_digest in PROVIDERS.items():
        assert sha(work / 'vendor-tree' / relative) == dependency_digest
        assert sha(work / 'vendor-readback' / relative) == dependency_digest
    for suffix in ('tree', 'readback'):
        assert sha(work / ('odm-' + suffix) / 'lib64/camera/aon_front.pb') == (
            'b0d920c16e4968173cf8f4f90c1056e959b9aad1c2651a76cca17ee19dac46d6')
        assert (work / ('vendor-' + suffix) / 'lib64/camera/aon_front.pb').readlink() == (
            Path('/odm/lib64/camera/aon_front.pb'))
    outputs['vbmeta'] = work / 'vbmeta.img'
    merge_parent(avb, avbtool, bases['vbmeta'], [trees['odm'], trees['vendor']],
                 outputs['vbmeta'], 'SHA256_RSA4096', work)
    validate(spec, workspace)
    assert sha(args.spec) == spec_digest and set(outputs) == set(OUTPUTS)
    bases_for(workspace)
    report = dict(revision=25, frozen_spec=spec, spec_sha256=spec_digest,
                  baseline_sha256={p: entry[2] for p, entry in PINNED.items()},
                  partition_reports=reports, work_dir=str(work),
                  exact_baselines_verified=True, all_filesystem_stages_verified=True,
                  both_changed_child_descriptors_verified=True,
                  hardware_boot_tested=False, runtime_verified=False)
    publish_batch(destination, outputs, report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
