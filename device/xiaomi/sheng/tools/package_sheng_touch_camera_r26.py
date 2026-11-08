#!/usr/bin/env python3
"""Seal exactly the no-wait touch module and camera orientation adapter over r25."""
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
from package_sheng_overlay_followup import complete_metadata

DEVICE = Path(__file__).resolve().parents[1]
PINNED = {
    'odm': ('r25', 1141067776, '933b205abe8bd856c62044a21e166097c288fadb56c18dd4c51099f104964ed7'),
    'vendor': ('r25', 303517696, '1033f2d63390dab9101d2fd97963d2a9f85cbcb872b71fb3f002c5b840fd29d3'),
    'vendor_dlkm': ('r26-baseline', 62590976, 'ade517337e3cef0cbb52eb1096ed46ceb98a97cec51b2d53c7f092c481ceae1f'),
    'vbmeta': ('r25', 8192, '844a09d6781156bbc1a63fbe8f20abb12b4cb8cf713b4e1e434826d2063815a3'),
}
SCOPE = {'odm': {'lib64/hw/camera.sheng.so'}, 'vendor': {'build.prop'},
         'vendor_dlkm': {'lib/modules/nt36532_touch.ko'}}
CAMERA_REVIEW = 'docs/r26-camera-orientation-review-20261108.json'
TOUCH_REVIEW = 'docs/r26-touch-zero-wait-validation-20261108.json'
PROP_OLD_SHA = '78f879ecf3452091f0cadf097be81d28002322de9f68237ec322a07a83d9ac0e'


def bases_for(workspace):
    bases = {p: workspace / f'artifacts/system-hardware-followup-sheng-{r}/{p}.img'
             for p, (r, _, _) in PINNED.items()}
    for p, image in bases.items():
        assert image.is_file() and not image.is_symlink()
        assert image.stat().st_size == PINNED[p][1] and sha(image) == PINNED[p][2], p
    return bases


def prop_bytes(workspace):
    original = workspace / 'artifacts/system-hardware-followup-sheng-r26-baseline/vendor-build.prop'
    assert sha(original) == PROP_OLD_SHA
    data = original.read_bytes()
    assert data.count(b'ro.hardware.camera=xiaomi\n') == 1
    assert b'ro.hardware.camera=sheng\n' in (DEVICE / 'properties/vendor.prop').read_bytes()
    return data.replace(b'ro.hardware.camera=xiaomi\n', b'ro.hardware.camera=sheng\n')


def prepare_outputs(workspace):
    camera = json.loads((DEVICE / CAMERA_REVIEW).read_text())
    touch = json.loads((DEVICE / TOUCH_REVIEW).read_text())
    assert camera['isolated_compile_passed'] and camera['synthetic_target_test_passed']
    assert all(touch['validation'].values()) and touch['new_delay_ms'] == 0
    module = ROM / 'out/target/product/sheng/obj/PACKAGING/kernel_modules_intermediates/lib/modules'
    modules = list(module.glob('*/extra/sheng/nt36532_touch.ko'))
    assert len(modules) == 1 and sha(modules[0]) == touch['patched_sha256']
    adapter = Path(camera['commands']).parent / 'camera.sheng.so'
    assert sha(adapter) == camera['output_sha256']['camera.sheng.so']
    for relative, digest in camera['source_sha256'].items():
        assert sha(DEVICE / relative) == digest
    destination = PRODUCT / 'vendor/build.prop'
    updated = prop_bytes(workspace)
    assert destination.read_bytes() in (
        (workspace / 'artifacts/system-hardware-followup-sheng-r26-baseline/vendor-build.prop').read_bytes(), updated)
    destination.write_bytes(updated)
    for p, relative, source in [('odm', 'lib64/hw/camera.sheng.so', adapter),
                                ('vendor_dlkm', 'lib/modules/nt36532_touch.ko', modules[0])]:
        target = PRODUCT / p / relative
        assert target.parent.is_dir() and not target.is_symlink()
        if target.exists():
            accepted = {sha(source)}
            if p == 'vendor_dlkm': accepted.add(touch['original_sha256'])
            assert sha(target) in accepted, target
        shutil.copyfile(source, target)


def validate(spec, workspace):
    assert spec['revision'] == 26 and set(spec['partitions']) == set(SCOPE)
    assert spec['baseline_sha256'] == {p: v[2] for p, v in PINNED.items()}
    camera = json.loads((DEVICE / CAMERA_REVIEW).read_text())
    touch = json.loads((DEVICE / TOUCH_REVIEW).read_text())
    assert camera['synthetic_target_test_passed'] and camera['isolated_compile_passed']
    assert camera['orientation_cases'] == 12 and camera['concurrent_cache_reads'] == 1600
    assert touch['new_delay_ms'] == 0 and all(touch['validation'].values())
    expected = {'odm': camera['output_sha256']['camera.sheng.so'],
                'vendor_dlkm': touch['patched_sha256']}
    for p, entry in spec['partitions'].items():
        assert set(entry['files']) == SCOPE[p]
        assert set(entry['new_nodes']) == ({'lib64/hw/camera.sheng.so'} if p == 'odm' else set())
        validate_inputs(p, entry['files'])
        for value in entry['files'].values():
            if p in expected: assert value['sha256'] == expected[p]
    assert (PRODUCT / 'vendor/build.prop').read_bytes() == prop_bytes(workspace)
    assert sha(PRODUCT / 'odm/lib64/hw/camera.xiaomi.so') == camera['original_camera_sha256']
    for relative, digest in camera['source_sha256'].items(): assert sha(DEVICE / relative) == digest
    for name in (CAMERA_REVIEW, TOUCH_REVIEW): assert spec['reviews_sha256'][name] == sha(DEVICE / name)
    assert set(source_paths(workspace)) == set(spec['device_inputs'])
    for p, digest in spec['device_inputs'].items():
        assert sha(DEVICE / p) == sha(workspace / 'device/xiaomi/sheng' / p) == digest, p
    validate_packaging_inputs(spec['partitions'], spec['build_inputs'])


def freeze(workspace, bases, output):
    assert not output.exists()
    metadata, _ = complete_metadata(bases['odm'])
    sibling = metadata['/lib64/hw/camera.xiaomi.so']
    node = {k: sibling[k] for k in ('uid', 'gid', 'mode', 'mtime_ns')}
    node['selinux'] = bytes.fromhex(sibling['xattrs']['6:selinux']).rstrip(b'\0').decode()
    partitions = {}
    for p, paths in SCOPE.items():
        files = {}
        for relative in paths:
            source = PRODUCT / p / relative
            files[relative] = dict(source=str(source), kind='file', bytes=source.stat().st_size, sha256=sha(source))
        partitions[p] = dict(files=files, new_nodes={'lib64/hw/camera.sheng.so': node} if p == 'odm' else {})
    keys = set().union(*(erofs_input_keys(p) for p in SCOPE))
    spec = dict(revision=26, partitions=partitions, baseline_sha256={p: v[2] for p, v in PINNED.items()},
                device_inputs={p: sha(DEVICE / p) for p in source_paths(workspace)},
                build_inputs={p: sha(packaging_input_path(p)) for p in sorted(keys)},
                reviews_sha256={p: sha(DEVICE / p) for p in (CAMERA_REVIEW, TOUCH_REVIEW)},
                source_commit=subprocess.check_output(['git', '-C', str(workspace), 'rev-parse', 'HEAD'], text=True).strip())
    validate(spec, workspace)
    with output.open('x') as stream: stream.write(json.dumps(spec, indent=2) + '\n')
    return spec


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
    if args.prepare_outputs: prepare_outputs(workspace)
    spec = freeze(workspace, bases, args.spec) if args.freeze_only else json.loads(args.spec.read_text())
    validate(spec, workspace)
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    _, _, root_descriptors, _ = parse_image(avb, avbtool, bases['vbmeta'])
    for p in SCOPE:
        _, _, _, tree = tree_descriptor(avb, avbtool, bases[p], p)
        selected = [d for d in root_descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == p]
        assert len(selected) == 1 and selected[0].encode() == tree.encode(), p
    if args.freeze_only or args.validate_only:
        print(json.dumps(dict(revision=26, validation_passed=True, spec_sha256=sha(args.spec))))
        return
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r26'
    assert not destination.exists()
    # Use tmpfs for POSIX symlinks and enough staging space without growing C:.
    # Only generated trees are temporary; sealed images and logs go to artifacts.
    assert shutil.disk_usage('/dev/shm').free > 7 * 1024**3
    work = Path(tempfile.mkdtemp(prefix='sheng-r26-', dir='/dev/shm'))
    outputs, trees, reports = {}, {}, {}
    for p, stage in spec['partitions'].items():
        print('Staging and independently reading back ' + p, flush=True)
        image, tree, report = stage_erofs(p, bases[p], stage['files'], stage['new_nodes'], work, avb, avbtool)
        assert set(report['changed_files']) == SCOPE[p] and report['metadata_preserved']
        if p == 'vendor': assert report['baseline_entries']['build.prop'] == ('file', PROP_OLD_SHA)
        if p == 'vendor_dlkm':
            assert report['baseline_entries']['lib/modules/nt36532_touch.ko'] == ('file',
                json.loads((DEVICE / TOUCH_REVIEW).read_text())['original_sha256'])
        if p == 'odm':
            assert report['baseline_entries']['lib64/hw/camera.sheng.so'] is None
            assert sha(work / 'odm-readback/lib64/hw/camera.xiaomi.so') == (
                json.loads((DEVICE / CAMERA_REVIEW).read_text())['original_camera_sha256'])
        outputs[p], trees[p], reports[p] = image, tree, report
    outputs['vbmeta'] = work / 'vbmeta.img'
    merge_parent(avb, avbtool, bases['vbmeta'], list(trees.values()), outputs['vbmeta'], 'SHA256_RSA4096', work)
    _, root_header, new_descriptors, _ = parse_image(avb, avbtool, outputs['vbmeta'])
    image = avbtool.ImageHandler(str(outputs['vbmeta']), read_only=True)
    try: blob = avb._load_vbmeta_blob(image)
    finally: image._image.close()
    assert avbtool.verify_vbmeta_signature(root_header, blob)
    assert [d.encode() for d in new_descriptors if getattr(d, 'partition_name', None) not in SCOPE] == [
        d.encode() for d in root_descriptors if getattr(d, 'partition_name', None) not in SCOPE]
    validate(spec, workspace)
    bases_for(workspace)
    evidence = workspace / 'artifacts' / ('r26-build-evidence-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    evidence.mkdir()
    for p in work.iterdir():
        if p.is_file() and p.suffix in ('.log', '.txt', '.bin'): shutil.copyfile(p, evidence / p.name)
    publish_batch(destination, outputs, dict(revision=26, frozen_spec=spec, spec_sha256=sha(args.spec),
        baseline_sha256={p: v[2] for p, v in PINNED.items()}, partition_reports=reports, work_dir=str(work),
        persistent_build_evidence_dir=str(evidence), temporary_work_on_tmpfs=True,
        exact_baselines_verified=True, all_filesystem_stages_verified=True, three_changed_child_descriptors_verified=True,
        root_signature_verified=True, root_other_descriptors_unchanged=True, original_systemui_required=True,
        hardware_boot_tested=False, runtime_verified=False))
    assert work.parent == Path('/dev/shm') and work.name.startswith('sheng-r26-')
    shutil.rmtree(work)
    print(destination)


if __name__ == '__main__':
    main()
