#!/usr/bin/env python3
"""Read-only supplemental AVB review of sealed r25 with accepted r22 SystemUI."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROM = Path('/root/sheng-lineage/lineage-24.0')
sys.path.insert(0, str(ROM / 'external/avb'))
import avbtool
from package_sheng_model_followup import parse_image, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    directory = workspace / 'artifacts'
    paths = {name: directory / f'system-hardware-followup-sheng-r{revision}' / file
             for name, revision, file in (
                 ('odm', 25, 'odm.img'), ('vendor', 25, 'vendor.img'),
                 ('vbmeta', 25, 'vbmeta.img'), ('old_root', 24, 'vbmeta.img'),
                 ('old_system_parent', 24, 'vbmeta_system.img'),
                 ('system_ext', 22, 'system_ext.img'),
                 ('vbmeta_system', 22, 'vbmeta_system.img'))}
    pinned = {
        'odm': '933b205abe8bd856c62044a21e166097c288fadb56c18dd4c51099f104964ed7',
        'vendor': '1033f2d63390dab9101d2fd97963d2a9f85cbcb872b71fb3f002c5b840fd29d3',
        'vbmeta': '844a09d6781156bbc1a63fbe8f20abb12b4cb8cf713b4e1e434826d2063815a3',
        'old_root': '883ba3ee6d22460c8a14f5a0eb04aabb4544d1d48d2386de52715b16ca7a9493',
        'old_system_parent': '644b62ff23dbf89775a5870b517d36a74fa13e9cefaa0d24a97ef5c9dea5014f',
        'system_ext': '82006f12228ebda0a521a96f8373c48bb52edb981a790830304f8ea50aa60419',
        'vbmeta_system': '3fe3413cc7fe8786372606ebfe7f9470e41bbf34b1dbcb5db7397540d9afc26a',
    }
    for name, path in paths.items():
        assert path.is_file() and not path.is_symlink() and sha(path) == pinned[name], name
    manifest_path = paths['vbmeta'].parent / 'build-result.json'
    manifest_hash = sha(manifest_path)
    assert manifest_hash == 'd2fb80197aa240404e238ac7c3e66a9e87b349e24fb811b3db55d8ab6cae3c94'
    avb = avbtool.Avb()
    parsed = {name: parse_image(avb, avbtool, path) for name, path in paths.items()}
    # Parent CLI verification resolves every sibling, including unchanged boot
    # images absent from these sealed directories. Verify each parent signature
    # directly, then explicitly compare the changed/preserved child descriptors.
    for name, path in paths.items():
        image = avbtool.ImageHandler(str(path), read_only=True)
        try:
            blob = avb._load_vbmeta_blob(image)
        finally:
            image._image.close()
        assert avbtool.verify_vbmeta_signature(parsed[name][1], blob), name
    for name in ('odm', 'vendor', 'system_ext'):
        subprocess.run([str(ROM / 'out/host/linux-x86/bin/avbtool'), 'verify_image',
                        '--image', str(paths[name])], check=True, capture_output=True)
    roots = parsed['vbmeta'][2]
    old_roots = parsed['old_root'][2]
    changed = {'odm', 'vendor'}
    assert [d.encode() for d in roots if getattr(d, 'partition_name', None) not in changed] == [
        d.encode() for d in old_roots if getattr(d, 'partition_name', None) not in changed]
    for name in ('odm', 'vendor'):
        expected = [d for d in parsed[name][2]
                    if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == name]
        actual = [d for d in roots if isinstance(d, avbtool.AvbHashtreeDescriptor)
                  and d.partition_name == name]
        assert len(actual) == len(expected) == 1 and actual[0].encode() == expected[0].encode()
    chains = [d for d in roots if isinstance(d, avbtool.AvbChainPartitionDescriptor)
              and d.partition_name == 'vbmeta_system']
    assert len(chains) == 1 and chains[0].rollback_index_location > 0
    header = parsed['vbmeta_system'][1]
    image = avbtool.ImageHandler(str(paths['vbmeta_system']), read_only=True)
    try:
        blob = avb._load_vbmeta_blob(image)
    finally:
        image._image.close()
    offset = avbtool.AvbVBMetaHeader.SIZE + header.authentication_data_block_size + header.public_key_offset
    key = blob[offset:offset + header.public_key_size]
    assert key and key == chains[0].public_key
    for name in ('system', 'system_ext'):
        accepted = [d for d in parsed['vbmeta_system'][2]
                    if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == name]
        other = parsed['old_system_parent' if name == 'system' else 'system_ext'][2]
        expected = [d for d in other if isinstance(d, avbtool.AvbHashtreeDescriptor)
                    and d.partition_name == name]
        assert len(accepted) == len(expected) == 1 and accepted[0].encode() == expected[0].encode()
    result = dict(supplemental_chain_review_passed=True, sealed_r25_images_unchanged=True,
                  original_systemui_required=True, changed_partitions=['odm', 'vendor', 'vbmeta'],
                  preserved_partitions=['system', 'system_ext', 'vbmeta_system'],
                  image_sha256=pinned, manifest_sha256=manifest_hash,
                  root_other_descriptors_unchanged=True, changed_child_descriptors_match=True,
                  accepted_system_parent_signature_verified=True,
                  accepted_system_parent_key_matches_root=True,
                  system_descriptor_unchanged=True, system_ext_descriptor_matches_accepted_image=True,
                  system_parent_key_sha256=hashlib.sha256(key).hexdigest(),
                  existing_startup_dolby_abort_unresolved=True, hardware_boot_tested=False)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
