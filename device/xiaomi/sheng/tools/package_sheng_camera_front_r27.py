#!/usr/bin/env python3
"""Seal the front mounting correction over the exact installed r26 ODM/root."""
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
PINNED = {
    'odm': (1141067776, 'c2bd108f940919f11c9b98ac2e0893d79c2b654f2b87032960250dcbeb7821eb'),
    'vbmeta': (8192, '9287340daa55149d2f1aa5a84c9a8086a6da80163e3c92af1c3b762edcc68208'),
}
RELATIVE = 'lib64/hw/camera.sheng.so'
OLD_ADAPTER = '1af026426ed133d440fe01bc3bf5c1ccb1cfe0317b5c962bef22f6f1677728bc'
REVIEW = 'docs/r27-camera-front-review-20261108.json'


def bases_for(workspace):
    bases = {p: workspace / f'artifacts/system-hardware-followup-sheng-r26/{p}.img' for p in PINNED}
    for p, image in bases.items():
        assert image.is_file() and not image.is_symlink()
        assert image.stat().st_size == PINNED[p][0] and sha(image) == PINNED[p][1], p
    return bases


def review():
    data = json.loads((DEVICE / REVIEW).read_text())
    assert data['isolated_compile_passed'] and data['synthetic_target_test_passed']
    assert data['back_orientation'] == [90, 0] and data['front_orientation'] == [270, 0]
    assert data['orientation_cases'] == 12 and data['concurrent_cache_reads'] == 1600
    assert data['prebuild_public_audit_passed'] and data['postbuild_public_audit_passed']
    for p, digest in data['source_sha256'].items(): assert sha(DEVICE / p) == digest
    adapter = Path(data['commands']).parent / 'camera.sheng.so'
    assert sha(adapter) == data['output_sha256']['camera.sheng.so']
    return data, adapter


def validate(spec, workspace):
    data, adapter = review()
    assert spec['revision'] == 27 and set(spec['partitions']) == {'odm'}
    assert spec['baseline_sha256'] == {p: v[1] for p, v in PINNED.items()}
    entry = spec['partitions']['odm']
    assert set(entry['files']) == {RELATIVE} and entry['new_nodes'] == {}
    validate_inputs('odm', entry['files'])
    assert entry['files'][RELATIVE]['sha256'] == sha(adapter)
    assert sha(PRODUCT / 'odm/lib64/hw/camera.xiaomi.so') == data['original_camera_sha256']
    assert spec['reviews_sha256'] == {REVIEW: sha(DEVICE / REVIEW)}
    assert set(source_paths(workspace)) == set(spec['device_inputs'])
    for p, digest in spec['device_inputs'].items():
        assert sha(DEVICE / p) == sha(workspace / 'device/xiaomi/sheng' / p) == digest, p
    validate_packaging_inputs(spec['partitions'], spec['build_inputs'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--prepare-outputs', action='store_true')
    parser.add_argument('--freeze-only', action='store_true')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    assert __debug__ and DEVICE.resolve() == ROM / 'device/xiaomi/sheng'
    workspace = args.workspace.resolve(strict=True)
    bases = bases_for(workspace)
    data, adapter = review()
    if args.prepare_outputs:
        target = PRODUCT / 'odm' / RELATIVE
        assert target.is_file() and not target.is_symlink() and sha(target) in {OLD_ADAPTER, sha(adapter)}
        shutil.copyfile(adapter, target)
    if args.freeze_only:
        assert not args.spec.exists()
        source = PRODUCT / 'odm' / RELATIVE
        spec = dict(revision=27, partitions={'odm': dict(files={RELATIVE: dict(
            source=str(source), kind='file', bytes=source.stat().st_size, sha256=sha(source))}, new_nodes={})},
            baseline_sha256={p: v[1] for p, v in PINNED.items()},
            device_inputs={p: sha(DEVICE / p) for p in source_paths(workspace)},
            build_inputs={p: sha(packaging_input_path(p)) for p in sorted(erofs_input_keys('odm'))},
            reviews_sha256={REVIEW: sha(DEVICE / REVIEW)},
            source_commit=subprocess.check_output(['git', '-C', str(workspace), 'rev-parse', 'HEAD'], text=True).strip())
        validate(spec, workspace)
        with args.spec.open('x') as stream: stream.write(json.dumps(spec, indent=2) + '\n')
    else:
        spec = json.loads(args.spec.read_text())
    validate(spec, workspace)
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    _, _, root_descriptors, _ = parse_image(avb, avbtool, bases['vbmeta'])
    _, _, _, tree = tree_descriptor(avb, avbtool, bases['odm'], 'odm')
    selected = [d for d in root_descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == 'odm']
    assert len(selected) == 1 and selected[0].encode() == tree.encode()
    if args.freeze_only or args.validate_only:
        print(json.dumps(dict(revision=27, validation_passed=True, spec_sha256=sha(args.spec))))
        return
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r27'
    assert not destination.exists() and shutil.disk_usage('/dev/shm').free > 5 * 1024**3
    work = Path(tempfile.mkdtemp(prefix='sheng-r27-', dir='/dev/shm'))
    stage = spec['partitions']['odm']
    print('Staging and independently reading back ODM', flush=True)
    image, tree, report = stage_erofs('odm', bases['odm'], stage['files'], stage['new_nodes'], work, avb, avbtool)
    assert set(report['changed_files']) == {RELATIVE} and report['metadata_preserved']
    assert report['baseline_entries'][RELATIVE] == ('file', OLD_ADAPTER)
    assert sha(work / 'odm-readback/lib64/hw/camera.xiaomi.so') == data['original_camera_sha256']
    outputs = {'odm': image, 'vbmeta': work / 'vbmeta.img'}
    merge_parent(avb, avbtool, bases['vbmeta'], [tree], outputs['vbmeta'], 'SHA256_RSA4096', work)
    _, root_header, new_descriptors, _ = parse_image(avb, avbtool, outputs['vbmeta'])
    handler = avbtool.ImageHandler(str(outputs['vbmeta']), read_only=True)
    try: blob = avb._load_vbmeta_blob(handler)
    finally: handler._image.close()
    assert avbtool.verify_vbmeta_signature(root_header, blob)
    assert [d.encode() for d in new_descriptors if getattr(d, 'partition_name', None) != 'odm'] == [
        d.encode() for d in root_descriptors if getattr(d, 'partition_name', None) != 'odm']
    validate(spec, workspace)
    bases_for(workspace)
    evidence = workspace / 'artifacts' / ('r27-build-evidence-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    evidence.mkdir()
    for p in work.iterdir():
        if p.is_file() and p.suffix in ('.log', '.txt', '.bin'): shutil.copyfile(p, evidence / p.name)
    publish_batch(destination, outputs, dict(revision=27, frozen_spec=spec, spec_sha256=sha(args.spec),
        baseline_sha256={p: v[1] for p, v in PINNED.items()}, partition_reports={'odm': report}, work_dir=str(work),
        persistent_build_evidence_dir=str(evidence), temporary_work_on_tmpfs=True,
        exact_baselines_verified=True, all_filesystem_stages_verified=True, one_changed_child_descriptor_verified=True,
        root_signature_verified=True, root_other_descriptors_unchanged=True, original_systemui_required=True,
        hardware_boot_tested=False, runtime_verified=False))
    assert work.parent == Path('/dev/shm') and work.name.startswith('sheng-r27-')
    shutil.rmtree(work)
    print(destination)


if __name__ == '__main__':
    main()
