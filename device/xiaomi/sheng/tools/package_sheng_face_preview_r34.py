#!/usr/bin/env python3
"""Seal the r34 HAL-owned face preview correction over verified r33."""
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
REVIEW = 'docs/r34-face-preview-build-review-20261108.json'
SCOPE = {'odm': {'overlay/SettingsResOverlaySheng.apk'}}
PINNED = {
    'odm': ('r32', 1141067776, 'b2feb95cfd5ecc0caf2d058c0edb082334e8c8a49848857198651f676e9dd80e'),
    'vbmeta': ('r33', 8192, '9f9d1b85de4fb25883d889845e76209357be91dc5311451dd6d9b4f3431e4d27'),
}


def bases_for(workspace):
    bases = {p: workspace / f'artifacts/system-hardware-followup-sheng-{r}/{p}.img'
             for p, (r, _, _) in PINNED.items()}
    for p, image in bases.items():
        assert image.is_file() and not image.is_symlink()
        assert image.stat().st_size == PINNED[p][1] and sha(image) == PINNED[p][2], p
    return bases


def validate(spec, workspace):
    review = json.loads((DEVICE / REVIEW).read_text())
    assert all(review.get(k) is True for k in ('scoped_module_build_passed',
'host_idmap_overlayable_enforced',
        'postbuild_public_audit_passed', 'target_resource_probe_passed'))
    assert review['full_product_build_passed'] is False
    assert spec['revision'] == 34 and set(spec['partitions']) == set(SCOPE)
    assert spec['baseline_sha256'] == {p: v[2] for p, v in PINNED.items()}
    assert spec['reviews_sha256'] == {REVIEW: sha(DEVICE / REVIEW)}
    for p, stage in spec['partitions'].items():
        assert set(stage['files']) == SCOPE[p] and stage['new_nodes'] == {}
        validate_inputs(p, stage['files'])
        for r, value in stage['files'].items():
            assert value['sha256'] == review['reviewed_sha256'][p][r]
    for r, digest in review['source_sha256'].items():
        assert sha(DEVICE / r) == digest, r
    assert set(source_paths(workspace)) == set(spec['device_inputs'])
    for r, digest in spec['device_inputs'].items():
        assert sha(DEVICE / r) == sha(workspace / 'device/xiaomi/sheng' / r) == digest, r
    validate_packaging_inputs(spec['partitions'], spec['build_inputs'])


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
    if args.freeze_only:
        assert not args.spec.exists()
        partitions = {}
        for p, paths in SCOPE.items():
            files = {r: dict(source=str(PRODUCT / p / r), kind='file',
                            bytes=(PRODUCT / p / r).stat().st_size,
                            sha256=sha(PRODUCT / p / r)) for r in sorted(paths)}
            partitions[p] = dict(files=files, new_nodes={})
        keys = set().union(*(erofs_input_keys(p) for p in SCOPE))
        spec = dict(revision=34, partitions=partitions,
            baseline_sha256={p: v[2] for p, v in PINNED.items()},
            device_inputs={r: sha(DEVICE / r) for r in source_paths(workspace)},
            build_inputs={r: sha(packaging_input_path(r)) for r in sorted(keys)},
            reviews_sha256={REVIEW: sha(DEVICE / REVIEW)},
            source_commit=subprocess.check_output(['git', '-C', str(workspace), 'rev-parse', 'HEAD'], text=True).strip())
        validate(spec, workspace)
        with args.spec.open('x') as stream: stream.write(json.dumps(spec, indent=2) + '\n')
    else:
        spec = json.loads(args.spec.read_text())
    validate(spec, workspace)
    digest = sha(args.spec)
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    _, _, descriptors, _ = parse_image(avb, avbtool, bases['vbmeta'])
    for child in SCOPE:
        _, _, _, tree = tree_descriptor(avb, avbtool, bases[child], child)
        selected = [d for d in descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)
                    and d.partition_name == child]
        assert len(selected) == 1 and selected[0].encode() == tree.encode(), child
    if args.freeze_only or args.validate_only:
        print(json.dumps(dict(revision=34, validation_passed=True, spec_sha256=digest)))
        return
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r34'
    assert not destination.exists() and shutil.disk_usage('/dev/shm').free > 7 * 1024**3
    work = Path(tempfile.mkdtemp(prefix='sheng-r34-', dir='/dev/shm'))
    outputs, trees, reports = {}, [], {}
    for p, stage in spec['partitions'].items():
        print('Staging and independently reading back ' + p, flush=True)
        outputs[p], tree, reports[p] = stage_erofs(p, bases[p], stage['files'], {}, work, avb, avbtool)
        trees.append(tree)
        assert set(reports[p]['changed_files']) == SCOPE[p] and reports[p]['metadata_preserved']
    outputs['vbmeta'] = work / 'vbmeta.img'
    merge_parent(avb, avbtool, bases['vbmeta'], trees, outputs['vbmeta'], 'SHA256_RSA4096', work)
    _, header, _, _ = parse_image(avb, avbtool, outputs['vbmeta'])
    handler = avbtool.ImageHandler(str(outputs['vbmeta']), read_only=True)
    try: blob = avb._load_vbmeta_blob(handler)
    finally: handler._image.close()
    assert avbtool.verify_vbmeta_signature(header, blob)
    validate(spec, workspace)
    bases_for(workspace)
    assert sha(args.spec) == digest
    evidence = workspace / 'artifacts' / ('r34-build-evidence-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    evidence.mkdir()
    for p in work.iterdir():
        if p.is_file() and p.suffix in ('.log', '.txt', '.bin'): shutil.copyfile(p, evidence / p.name)
    publish_batch(destination, outputs, dict(revision=34, frozen_spec=spec, spec_sha256=digest,
        baseline_sha256={p: v[2] for p, v in PINNED.items()}, partition_reports=reports,
        exact_baselines_verified=True, all_filesystem_stages_verified=True,
        root_signature_verified=True, root_other_descriptors_unchanged=True,
        original_systemui_required=True, system_ext_and_vbmeta_system_unchanged=True,
        persistent_build_evidence_dir=str(evidence), temporary_work_on_tmpfs=True,
        hardware_boot_tested=False, runtime_verified=False))
    assert work.parent == Path('/dev/shm') and work.name.startswith('sheng-r34-')
    shutil.rmtree(work)
    print(destination)


if __name__ == '__main__': main()
