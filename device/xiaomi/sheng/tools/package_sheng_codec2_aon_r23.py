#!/usr/bin/env python3
"""Freeze/package only the r23 Dolby executables and stock AON vendor alias."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from freeze_sheng_batch_inputs import CompiledContexts, erofs_new_nodes
from package_sheng_batch_helpers import (
    erofs_input_keys, merge_parent, packaging_input_path, publish_batch,
    stage_erofs, tree_descriptor, validate_inputs, validate_packaging_inputs,
)
from package_sheng_color_functions import source_paths
from package_sheng_model_followup import HOST, PRODUCT, ROM, parse_image, sha

DEVICE = Path(__file__).resolve().parents[1]
PINNED = {
    'vendor': ('r21', 303517696, '210bf6f64bc865a8f6834e5b4b1d6fdd965139fec2cef2fda56b9fe978d5fd27'),
    'odm': ('r22', 1141067776, 'c315f3e80f292909740d3e052102dcabb36b3f3bcaa817918f9dbc92630ce651'),
    'vbmeta': ('r22', 8192, '37c3db81b769c3d872f04eee2ac778be77e70a5e47aa141a9e27215cafec6b4d'),
}
ALIAS = 'lib64/camera/aon_front.pb'
LINK = '/odm/' + ALIAS
TARGET_SHA = 'b0d920c16e4968173cf8f4f90c1056e959b9aad1c2651a76cca17ee19dac46d6'
SCOPE = {'bin/hw/dolbycodec2', 'bin/hw/vendor.dolby.media.c2@1.0-service', ALIAS}
OUTPUTS = {p: PINNED[p][1] for p in ('vendor', 'vbmeta')}


def bases_for(workspace):
    bases = {p: workspace / f'artifacts/system-hardware-followup-sheng-{release}/{p}.img'
             for p, (release, _, _) in PINNED.items()}
    for p, path in bases.items():
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_size == PINNED[p][1] and sha(path) == PINNED[p][2], p
    return bases


def validate(spec, workspace):
    build = json.loads((DEVICE / 'docs/build-r23-codec2-aon-20261107.json').read_text())
    assert build['build_passed'] and build['helper_tests_passed'] and build['upstream_audit_passed']
    assert set(spec) == {'revision', 'partitions', 'device_inputs', 'build_inputs', 'source_commit',
                         'expected_outputs', 'external_target', 'build_review_sha256'}
    assert spec['revision'] == 23 and spec['expected_outputs'] == OUTPUTS
    assert spec['build_review_sha256'] == sha(DEVICE / 'docs/build-r23-codec2-aon-20261107.json')
    assert spec['external_target'] == dict(path=LINK, sha256=TARGET_SHA, baseline_sha256=PINNED['odm'][2])
    assert set(spec['partitions']) == {'vendor'}
    stage = spec['partitions']['vendor']
    assert set(stage) == {'files', 'new_nodes'} and set(stage['files']) == SCOPE
    assert set(stage['new_nodes']) in ({ALIAS}, {'lib64/camera', ALIAS})
    for relative, entry in stage['files'].items():
        assert entry['sha256'] == build['reviewed_sha256'][relative], relative
        if relative == ALIAS:
            assert entry['kind'] == 'symlink' and entry['link_target'] == LINK
            assert entry['target_sha256'] == TARGET_SHA
        else:
            assert entry['kind'] == 'file'
    validate_inputs('vendor', stage['files'], allow_symlinks=True)
    validate_packaging_inputs(spec['partitions'], spec['build_inputs'])
    assert set(source_paths(workspace)) == set(spec['device_inputs'])
    for rel, digest in spec['device_inputs'].items():
        assert sha(DEVICE / rel) == sha(workspace / 'device/xiaomi/sheng' / rel) == digest, rel


def freeze(workspace, path, bases):
    assert not path.exists(), 'Never overwrite frozen inputs'
    entries = {}
    for rel in sorted(SCOPE):
        source = PRODUCT / 'vendor' / rel
        if rel == ALIAS:
            assert source.is_symlink() and os.readlink(source) == LINK
            entries[rel] = dict(source=str(source), kind='symlink', link_target=LINK,
                                bytes=len(LINK), sha256=hashlib.sha256(LINK.encode()).hexdigest(),
                                target_sha256=TARGET_SHA)
        else:
            entries[rel] = dict(source=str(source), kind='file', bytes=source.stat().st_size,
                                sha256=sha(source))
    with CompiledContexts(packaging_input_path('@sepolicy_file_contexts').read_bytes()) as labels:
        nodes = erofs_new_nodes('vendor', bases['vendor'], entries, labels)
    spec = dict(revision=23, partitions={'vendor': dict(files=entries, new_nodes=nodes)},
                expected_outputs=OUTPUTS,
                external_target=dict(path=LINK, sha256=TARGET_SHA, baseline_sha256=PINNED['odm'][2]),
                device_inputs={p: sha(DEVICE / p) for p in source_paths(workspace)},
                build_inputs={p: sha(packaging_input_path(p)) for p in sorted(erofs_input_keys('vendor'))},
                source_commit=subprocess.check_output(['git', '-C', str(workspace), 'rev-parse', 'HEAD'], text=True).strip(),
                build_review_sha256=sha(DEVICE / 'docs/build-r23-codec2-aon-20261107.json'))
    validate(spec, workspace)
    with path.open('x') as stream:
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
    spec = freeze(workspace, args.spec, bases) if args.freeze_only else json.loads(args.spec.read_text())
    validate(spec, workspace)
    digest = sha(args.spec)
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    _, _, _, tree = tree_descriptor(avb, avbtool, bases['vendor'], 'vendor')
    _, _, descriptors, _ = parse_image(avb, avbtool, bases['vbmeta'])
    selected = [d for d in descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)
                and d.partition_name == 'vendor']
    assert len(selected) == 1 and selected[0].encode() == tree.encode()
    if args.freeze_only or args.validate_only:
        print(json.dumps(dict(revision=23, spec_sha256=digest, validation_passed=True)))
        return
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r23'
    assert not destination.exists(), 'Never overwrite a published batch'
    work = Path('/root/sheng-lineage/hardware-followup') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-codec2-aon-r23')
    work.mkdir(parents=True)
    # Establish the external link target from the exact immutable installed ODM
    # baseline, independently of the build output used for input validation.
    target_root = work / 'odm-target-baseline'
    subprocess.run([HOST / 'fsck.erofs', '-d0', '--extract=' + str(target_root), '--preserve', bases['odm']],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    target = target_root / ALIAS
    assert target.is_file() and not target.is_symlink() and sha(target) == TARGET_SHA
    stage = spec['partitions']['vendor']
    image, replacement, filesystem = stage_erofs('vendor', bases['vendor'], stage['files'],
        stage['new_nodes'], work, avb, avbtool, external_symlink_targets={LINK: TARGET_SHA})
    assert set(filesystem['changed_files']) == SCOPE
    parent = work / 'vbmeta.img'
    merge_parent(avb, avbtool, bases['vbmeta'], [replacement], parent, 'SHA256_RSA4096', work)
    validate(spec, workspace)
    assert sha(args.spec) == digest
    bases_for(workspace)
    report = dict(revision=23, frozen_spec=spec, spec_sha256=digest,
                  baseline_sha256={p: values[2] for p, values in PINNED.items()},
                  partition_reports={'vendor': filesystem}, work_dir=str(work),
                  exact_baselines_verified=True, all_filesystem_stages_verified=True,
                  parent_chain_verified=True, external_target_baseline_verified=True,
                  hardware_boot_tested=False, runtime_verified=False)
    publish_batch(destination, {'vendor': image, 'vbmeta': parent}, report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
