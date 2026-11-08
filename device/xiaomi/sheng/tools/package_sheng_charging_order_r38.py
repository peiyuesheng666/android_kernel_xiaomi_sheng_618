#!/usr/bin/env python3
"""Seal the charging action-order repair over the exact verified r37 images."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from package_sheng_batch_helpers import (
    erofs_input_keys, merge_parent, packaging_input_path, publish_batch,
    stage_erofs, tree_descriptor, validate_inputs, validate_packaging_inputs,
)
from package_sheng_color_functions import source_paths
from package_sheng_model_followup import PRODUCT, ROM, parse_image, sha

DEVICE = Path(__file__).resolve().parents[1]
REVIEW = 'docs/r38-charging-order-build-review-20261108.json'
SCOPE = {'vendor': {'etc/init/init.sm8550.rc'}}
PINNED = {
    'vendor': (352321536, '3d6fa51b783c96c7ad8d45bea1dcd5ad6cf9fca9dcf80c5cec6fe56898fd4663'),
    'vbmeta': (8192, '75b740055de5cb55ee5e5d47d80f003ae7215bc376a1a2d048d07b747d9bf6fc'),
}


def bases_for(workspace):
    result = {p: workspace / 'artifacts/system-hardware-followup-sheng-r37' / (p + '.img')
              for p in PINNED}
    for p, path in result.items():
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_size == PINNED[p][0] and sha(path) == PINNED[p][1], p
    return result


def validate(spec, workspace):
    review = json.loads((DEVICE / REVIEW).read_text())
    for key in ('scoped_configuration_assembly_passed', 'host_init_verifier_passed',
                'exact_action_move_verified', 'prebuild_public_audit_passed',
                'postbuild_public_audit_passed'):
        assert review[key] is True, key
    assert review['full_product_build_passed'] is False and review['charging_value_written'] is False
    assert spec['revision'] == 38 and set(spec['partitions']) == set(SCOPE)
    assert spec['baseline_sha256'] == {p: v[1] for p, v in PINNED.items()}
    assert spec['reviews_sha256'] == {REVIEW: sha(DEVICE / REVIEW)}
    for p, stage in spec['partitions'].items():
        assert set(stage['files']) == SCOPE[p] and not stage['new_nodes']
        validate_inputs(p, stage['files'])
        for relative, value in stage['files'].items():
            assert value['sha256'] == review['reviewed_sha256'][p][relative]
    for relative, digest in review['source_sha256'].items():
        assert sha(DEVICE / relative) == digest, relative
    assert set(source_paths(workspace)) == set(spec['device_inputs'])
    for relative, digest in spec['device_inputs'].items():
        assert sha(DEVICE / relative) == sha(workspace / 'device/xiaomi/sheng' / relative) == digest, relative
    validate_packaging_inputs(spec['partitions'], spec['build_inputs'])


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
    if args.freeze_only:
        assert not args.spec.exists()
        partitions = {p: dict(files={r: dict(source=str(PRODUCT / p / r), kind='file',
            bytes=(PRODUCT / p / r).stat().st_size, sha256=sha(PRODUCT / p / r)) for r in sorted(paths)},
            new_nodes={}) for p, paths in SCOPE.items()}
        keys = set().union(*(erofs_input_keys(p) for p in SCOPE))
        spec = dict(revision=38, partitions=partitions,
            baseline_sha256={p: v[1] for p, v in PINNED.items()},
            device_inputs={r: sha(DEVICE / r) for r in source_paths(workspace)},
            build_inputs={r: sha(packaging_input_path(r)) for r in sorted(keys)},
            reviews_sha256={REVIEW: sha(DEVICE / REVIEW)},
            source_commit=subprocess.check_output(['git', '-C', str(workspace), 'rev-parse', 'HEAD'], text=True).strip())
        validate(spec, workspace)
        with args.spec.open('x') as stream:
            stream.write(json.dumps(spec, indent=2) + '\n')
    else:
        spec = json.loads(args.spec.read_text())
    validate(spec, workspace)
    digest = sha(args.spec)
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    _, _, descriptors, _ = parse_image(avb, avbtool, bases['vbmeta'])
    _, _, _, tree = tree_descriptor(avb, avbtool, bases['vendor'], 'vendor')
    selected = [d for d in descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)
                and d.partition_name == 'vendor']
    assert len(selected) == 1 and selected[0].encode() == tree.encode()
    if args.freeze_only or args.validate_only:
        print(json.dumps(dict(revision=38, validation_passed=True, spec_sha256=digest)))
        return
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r38'
    assert not destination.exists() and shutil.disk_usage('/dev/shm').free > 4 * 1024**3
    work = Path(tempfile.mkdtemp(prefix='sheng-r38-', dir='/dev/shm'))
    stage = spec['partitions']['vendor']
    image, tree, report = stage_erofs('vendor', bases['vendor'], stage['files'], {}, work, avb, avbtool,
                                      partition_size=352321536)
    assert set(report['changed_files']) == SCOPE['vendor'] and report['metadata_preserved']
    assert report['free_payload_bytes'] >= 33554432
    outputs = dict(vendor=image, vbmeta=work / 'vbmeta.img')
    merge_parent(avb, avbtool, bases['vbmeta'], [tree], outputs['vbmeta'], 'SHA256_RSA4096', work)
    _, header, _, _ = parse_image(avb, avbtool, outputs['vbmeta'])
    handler = avbtool.ImageHandler(str(outputs['vbmeta']), read_only=True)
    try:
        blob = avb._load_vbmeta_blob(handler)
    finally:
        handler._image.close()
    assert avbtool.verify_vbmeta_signature(header, blob)
    validate(spec, workspace)
    bases_for(workspace)
    assert sha(args.spec) == digest
    evidence = workspace / 'artifacts' / ('r38-build-evidence-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    evidence.mkdir()
    for path in work.iterdir():
        if path.is_file() and path.suffix in ('.log', '.txt', '.bin'):
            shutil.copyfile(path, evidence / path.name)
    publish_batch(destination, outputs, dict(revision=38, frozen_spec=spec, spec_sha256=digest,
        baseline_sha256={p: v[1] for p, v in PINNED.items()}, partition_reports={'vendor': report},
        exact_baselines_verified=True, all_filesystem_stages_verified=True,
        root_signature_verified=True, root_other_descriptors_unchanged=True,
        original_systemui_required=True, system_ext_and_vbmeta_system_unchanged=True,
        persistent_build_evidence_dir=str(evidence), temporary_work_on_tmpfs=True,
        hardware_boot_tested=False, runtime_verified=False))
    assert work.parent == Path('/dev/shm') and work.name.startswith('sheng-r38-')
    shutil.rmtree(work)
    print(destination)


if __name__ == '__main__':
    main()
