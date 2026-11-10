#!/usr/bin/env python3
"""Seal reviewed r39 defaults over the exact restored A-slot r38 image set."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile

from freeze_sheng_batch_inputs import CompiledContexts
from package_sheng_batch_helpers import (
    certificates, debugfs, erofs_input_keys, ext4_snapshot, inode_number,
    merge_parent, packaging_input_path, publish_batch, stage_erofs, stage_ext4,
    tree_descriptor, validate_packaging_inputs,
)
from package_sheng_model_followup import HOST, PRODUCT, ROM, parse_image, sha

SCOPE = {
    'odm': {'overlay/FrameworkResOverlaySheng.apk', 'overlay/LineageResOverlaySheng.apk'},
    'system_ext': {'priv-app/ShengDisplayDefaults/ShengDisplayDefaults.apk'},
}
PINNED = {
    'odm': '56ab11ae8b2ad2de585799d21c9e19fccb9922485b524bff3ed130794e440396',
    'system_ext': 'ccda96e9d2590f4aebf8327e9d2fa1f21ec4358cdd4d78add1557d3d0443263c',
    'vbmeta': 'b744a9853c080672f2f906b12e12a32449dfddbd4a82215c49167c16e74b0fe7',
    'vbmeta_system': '2aba140be1ae25ea56f409c715e0296207f4caf9ae317815a5cda458d2d0b998',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--build-review', type=Path, required=True)
    parser.add_argument('--post-audit', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__
    workspace = args.workspace.resolve(strict=True)
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r39'
    assert not destination.exists()
    build = json.loads(args.build_review.read_text())
    audit = json.loads(args.post_audit.read_text())
    assert build['scoped_build_passed'] and build['overlayable_policy_enforced']
    assert not build['systemui_changed'] and not build['full_product_build_passed']
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(audit['date_utc']).timestamp() < 7200
    for path, digest in build['sources_sha256'].items():
        assert sha(Path(path)) == digest, path
    manifest = json.loads((workspace / 'reports/device/r38-restore-20261110/restore-manifest.json').read_text())
    assert manifest['complete_avb_chain_verified'] and manifest['restore_slot'] == 'a'
    all_bases = {e['partition']: workspace / e['path'] for e in manifest['files']}
    bases = {p: all_bases[p] for p in PINNED}
    for entry in manifest['files']:
        path = all_bases[entry['partition']]
        assert path.stat().st_size == entry['bytes'] and sha(path) == entry['sha256']
    assert {p: sha(path) for p, path in bases.items()} == PINNED
    assert set(build['payload']) == {p + '/' + r for p, paths in SCOPE.items() for r in paths}
    assert shutil.disk_usage('/dev/shm').free > 7 * 1024**3
    work = Path(tempfile.mkdtemp(prefix='sheng-r39-', dir='/dev/shm'))
    # Stage hash-reviewed scoped build outputs at their normal installed paths.
    # Preserve the previous build outputs as evidence before replacing them.
    backup = work / 'previous-installed-outputs'
    entries = {}
    for partition, paths in SCOPE.items():
        entries[partition] = {}
        for relative in sorted(paths):
            payload = build['payload'][partition + '/' + relative]
            source, installed = Path(payload['path']), PRODUCT / partition / relative
            assert source.is_file() and not source.is_symlink() and sha(source) == payload['sha256']
            if installed.exists():
                old = backup / partition / relative
                old.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(installed, old)
            installed.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, installed)
            entries[partition][relative] = dict(source=str(installed), kind='file',
                bytes=installed.stat().st_size, sha256=sha(installed))
            assert sha(installed) == payload['sha256']
    snapshot = ext4_snapshot(bases['system_ext'])
    parent = snapshot['inodes'][inode_number(bases['system_ext'], '/priv-app')]
    assert stat.S_ISDIR(struct.unpack_from('<H', parent)[0])
    seconds = struct.unpack_from('<I', parent, 12)[0] + ((struct.unpack_from('<I', parent, 136)[0] & 3) << 32)
    nodes = {}
    with CompiledContexts(packaging_input_path('@sepolicy_file_contexts').read_bytes()) as labels:
        for relative in {'priv-app/ShengDisplayDefaults'} | SCOPE['system_ext']:
            directory = relative == 'priv-app/ShengDisplayDefaults'
            label = labels.lookup('/system_ext/' + relative, stat.S_IFDIR if directory else stat.S_IFREG)
            assert label == 'u:object_r:system_file:s0'
            nodes[relative] = dict(uid=0, gid=0, mode=0o755 if directory else 0o644,
                                  mtime_ns=seconds * 1_000_000_000, selinux=label)
    build_inputs = {r: sha(packaging_input_path(r)) for r in erofs_input_keys('odm')}
    validate_packaging_inputs(SCOPE, build_inputs)
    spec = dict(revision=39, baseline_sha256=PINNED, entries=entries, new_nodes=nodes,
                build_inputs=build_inputs, build_review_sha256=sha(args.build_review),
                postaudit_sha256=sha(args.post_audit), packer_sha256=sha(Path(__file__)),
                source_commit=subprocess.check_output(['git', '-C', workspace, 'rev-parse', 'HEAD'], text=True).strip())
    (work / 'frozen-spec.json').write_text(json.dumps(spec, indent=2) + '\n')
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    for p in SCOPE:
        _, _, _, tree = tree_descriptor(avb, avbtool, bases[p], p)
        parent = bases['vbmeta_system' if p == 'system_ext' else 'vbmeta']
        _, _, descriptors, _ = parse_image(avb, avbtool, parent)
        selected = [d for d in descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == p]
        assert len(selected) == 1 and selected[0].encode() == tree.encode()
    reference = work / 'platform-reference.apk'
    debugfs(bases['system_ext'], f'dump /priv-app/SystemUI/SystemUI.apk {reference}')
    assert sha(reference) == '33017b0d59e28da5db3e089a98f49601de508228a012392ee2d04c82cda3ccb1'
    outputs, replacements, reports = {}, {}, {}
    for p in SCOPE:
        common = p, bases[p], entries[p], nodes if p == 'system_ext' else {}, work, avb, avbtool
        image, tree, report = (stage_ext4(*common, certificates(reference)) if p == 'system_ext'
                               else stage_erofs(*common))
        assert set(report['changed_files']) == SCOPE[p] and report['metadata_preserved']
        outputs[p], replacements[p], reports[p] = image, tree, report
    for parent, p, algorithm in [('vbmeta', 'odm', 'SHA256_RSA4096'),
                                 ('vbmeta_system', 'system_ext', 'SHA256_RSA2048')]:
        outputs[parent] = work / (parent + '.img')
        merge_parent(avb, avbtool, bases[parent], [replacements[p]], outputs[parent], algorithm, work)
    chain = work / 'complete-chain'
    chain.mkdir()
    for p, path in all_bases.items():
        (chain / (p + '.img')).symlink_to(outputs.get(p, path).resolve())
    result = subprocess.run([HOST / 'avbtool', 'verify_image', '--image', chain / 'vbmeta.img',
                             '--follow_chain_partitions'], capture_output=True, text=True)
    (work / 'complete-chain.avb.txt').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    validate_packaging_inputs(SCOPE, build_inputs)
    for path, digest in build['sources_sha256'].items():
        assert sha(Path(path)) == digest
    assert {p: sha(path) for p, path in bases.items()} == PINNED
    evidence = workspace / 'artifacts' / ('r39-build-evidence-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    evidence.mkdir()
    for path in work.iterdir():
        if path.is_file() and path.suffix in ('.log', '.txt', '.bin', '.json'):
            shutil.copyfile(path, evidence / path.name)
    if backup.exists():
        shutil.copytree(backup, evidence / backup.name)
    publish_batch(destination, outputs, dict(revision=39, frozen_spec=spec, partition_reports=reports,
        exact_baselines_verified=True, all_filesystem_stages_verified=True,
        complete_avb_chain_verified=True, original_systemui_unchanged=True,
        full_product_build_passed=False, hardware_boot_tested=False, runtime_verified=False,
        persistent_build_evidence_dir=str(evidence), work_dir=str(work)))
    print(destination, flush=True)


if __name__ == '__main__':
    main()
