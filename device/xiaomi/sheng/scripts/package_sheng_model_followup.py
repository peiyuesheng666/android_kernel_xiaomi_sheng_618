#!/usr/bin/env python3
"""Package a model-name-only system delta over the exact installed raw base.

Public source and input images are read-only. This local development helper
does not replace normal device-tree builds or flash any partition.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys

DEVICE = Path(__file__).resolve().parents[1]
WORKSPACE = DEVICE.parents[2]
ROM = Path('/root/sheng-lineage/lineage-24.0')
PRODUCT = ROM / 'out/target/product/sheng'
HOST = ROM / 'out/host/linux-x86/bin'
EXPECTED_RAW_BYTES = 1005133824
EXPECTED_RAW_SHA = 'f89b07d973531ceea3d2d3a695754065382947b401393d382862f3b44a03aea4'
EXPECTED_VBMETA_SHA = 'cbc5326ebc2529cb108ff0673357c3fd6f3b44096ed42dbd00e0a7742833f06b'
TARGET_MODEL = b'Xiaomi Pad 6S Pro 12.4'
PROP_PATH = '/system/build.prop'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(command, **kwargs):
    environment = dict(os.environ, PATH=str(HOST) + ':' + os.environ['PATH'],
                       LANG='C.UTF-8', LC_ALL='C.UTF-8')
    return subprocess.run(list(map(str, command)), check=True, env=environment, **kwargs)


def debugfs(image, command):
    result = run(['debugfs', '-R', command, image], capture_output=True, text=True)
    # debugfs sometimes exits successfully even when an individual command fails.
    assert not any(message in result.stderr for message in
                   ('File not found', 'Command not found', 'Filesystem not open'))
    return result.stdout


def parse_image(avb, avbtool, path):
    return avb._parse_image(avbtool.ImageHandler(str(path), read_only=True))


def model_values(data):
    values = {}
    for line in data.splitlines():
        if line.startswith(b'ro.product.model=') or line.startswith(b'ro.product.system.model='):
            key, value = line.split(b'=', 1)
            assert key not in values, 'Duplicate model property'
            values[key] = value
    return values


def changed_blocks(before, after, size, block_size):
    differences = []
    with before.open('rb') as left, after.open('rb') as right:
        for start in range(0, size, 8 * 1024 * 1024):
            amount = min(8 * 1024 * 1024, size - start)
            a, b = left.read(amount), right.read(amount)
            assert len(a) == len(b) == amount
            if a == b:
                continue
            for offset in range(0, amount, block_size):
                if a[offset:offset + block_size] != b[offset:offset + block_size]:
                    differences.append((start + offset) // block_size)
    return differences


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw-base', type=Path, required=True,
                        help='Exact installed system_b raw image, pinned by SHA256')
    parser.add_argument('--prepare-only', action='store_true',
                        help='Validate/read inputs without packaging or modifying an image')
    parser.add_argument('--revision', type=int, default=7)
    parser.add_argument('--workspace', type=Path, default=WORKSPACE,
                        help='Artifact workspace when running the synced WSL source copy')
    args = parser.parse_args()
    assert args.revision >= 7
    baseline = args.raw_base.resolve()
    assert baseline.is_file() and baseline.stat().st_size == EXPECTED_RAW_BYTES
    assert sha(baseline) == EXPECTED_RAW_SHA, 'Raw base does not match installed system_b'
    workspace = args.workspace.resolve()
    base_vbmeta = workspace / 'artifacts/system-hardware-followup-sheng-r5/vbmeta_system.img'
    assert sha(base_vbmeta) == EXPECTED_VBMETA_SHA
    destination = workspace / f'artifacts/system-hardware-followup-sheng-r{args.revision}'
    assert not destination.exists(), 'Never overwrite a built/flashed revision'

    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    footer, old_image_header, image_descriptors, _ = parse_image(avb, avbtool, baseline)
    _, old_chain_header, chain_descriptors, _ = parse_image(avb, avbtool, base_vbmeta)
    old_image_system = [d for d in image_descriptors
                        if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == 'system']
    old_chain_system = [d for d in chain_descriptors
                        if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == 'system']
    assert len(old_image_system) == len(old_chain_system) == 1
    system_descriptor = old_image_system[0]
    assert system_descriptor.encode() == old_chain_system[0].encode(), 'Installed system AVB descriptor mismatch'
    assert footer and footer.original_image_size == system_descriptor.image_size
    assert old_image_header.algorithm_type == 0 and old_image_header.flags == 0
    assert system_descriptor.flags == 0 and system_descriptor.dm_verity_version == 1
    assert system_descriptor.data_block_size == system_descriptor.hash_block_size == 4096
    assert system_descriptor.fec_num_roots == 2
    assert old_chain_header.algorithm_type == avbtool.ALGORITHMS['SHA256_RSA2048'].algorithm_type
    assert old_chain_header.public_key_metadata_size == 0
    assert old_image_header.public_key_metadata_size == 0

    stat_before = debugfs(baseline, f'stat {PROP_PATH}')
    xattrs_before = debugfs(baseline, f'ea_list {PROP_PATH}')
    imap = debugfs(baseline, f'imap {PROP_PATH}')
    blocks = list(map(int, debugfs(baseline, f'blocks {PROP_PATH}').split()))
    stat_match = re.search(r'Inode:\s*(\d+).*?Mode:\s*(\d+)', stat_before)
    size_match = re.search(r'Project:\s*\d+\s+Size:\s*(\d+)', stat_before)
    inode_match = re.search(r'located at block (\d+), offset (0x[0-9a-f]+)', imap)
    assert stat_match and size_match and inode_match
    old_size = int(size_match[1])
    with baseline.open('rb') as source:
        source.seek(1024)
        superblock = source.read(1024)
        assert struct.unpack_from('<H', superblock, 56)[0] == 0xEF53
        block_size = 1024 << struct.unpack_from('<I', superblock, 24)[0]
        inode_size = struct.unpack_from('<H', superblock, 88)[0]
        # This exact base has no metadata_csum; editing inode size must not omit
        # recalculation on another filesystem variant.
        assert not (struct.unpack_from('<I', superblock, 100)[0] & 0x400), 'metadata_csum unsupported'
        assert block_size == 4096 and inode_size == 256
        inode_offset = int(inode_match[1]) * block_size + int(inode_match[2], 16)
        source.seek(inode_offset)
        inode_before = source.read(inode_size)
        assert len(inode_before) == inode_size
        assert struct.unpack_from('<I', inode_before, 4)[0] == old_size
        assert struct.unpack_from('<I', inode_before, 108)[0] == 0
    assert len(blocks) == (old_size + block_size - 1) // block_size
    assert len(blocks) == len(set(blocks)) and len(blocks) > 0
    assert all(block * block_size + block_size <= system_descriptor.image_size for block in blocks)

    work = Path('/root/sheng-lineage/hardware-followup') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-model')
    work.mkdir(parents=True)
    original_prop = work / 'original-build.prop'
    debugfs(baseline, f'dump {PROP_PATH} {original_prop}')
    original = original_prop.read_bytes()
    assert len(original) == old_size
    with baseline.open('rb') as source:
        raw_data = bytearray()
        for block in blocks:
            source.seek(block * block_size)
            raw_data.extend(source.read(block_size))
    assert bytes(raw_data[:old_size]) == original, 'File block order does not match build.prop dump'
    assert model_values(original).get(b'ro.product.system.model') == b'24018RPACC'
    prerequisites = dict(raw_base=str(baseline), raw_base_sha256=EXPECTED_RAW_SHA,
                         vbmeta_system_base_sha256=EXPECTED_VBMETA_SHA,
                         baseline_descriptor_matches_installed_chain=True,
                         system_build_prop_inode=int(stat_match[1]),
                         system_build_prop_mode=stat_match[2],
                         system_build_prop_blocks=blocks,
                         system_build_prop_inode_byte_offset=inode_offset,
                         original_build_prop_bytes=old_size,
                         original_model_properties={k.decode(): v.decode() for k, v in model_values(original).items()},
                         work_dir=str(work))
    if args.prepare_only:
        print(json.dumps(prerequisites, indent=2))
        return

    compiled_prop = PRODUCT / 'system/build.prop'
    compiled = compiled_prop.read_bytes()
    assert model_values(compiled) == {b'ro.product.model': TARGET_MODEL,
                                      b'ro.product.system.model': b'24018RPACC'}, 'Compiled model properties not ready'
    replacement = b'ro.product.model=' + TARGET_MODEL
    lines = original.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.startswith(b'ro.product.model=')]
    assert len(matches) <= 1
    if matches:
        index = matches[0]
        old_line = lines[index]
        newline = b'\r\n' if old_line.endswith(b'\r\n') else (b'\n' if old_line.endswith(b'\n') else b'')
        lines[index] = replacement + newline
        reverted = list(lines)
        reverted[index] = old_line
        assert b''.join(reverted) == original
    else:
        indices = [index for index, line in enumerate(lines) if line.startswith(b'ro.product.system.model=')]
        assert len(indices) == 1 and lines[indices[0]].endswith(b'\n')
        index = indices[0] + 1
        lines.insert(index, replacement + b'\n')
        reverted = list(lines)
        del reverted[index]
        assert b''.join(reverted) == original
    updated = b''.join(lines)
    assert updated != original and model_values(updated) == model_values(compiled)
    assert len(updated) <= len(raw_data), 'Model-only update must retain existing allocated blocks'
    updated_prop = work / 'updated-build.prop'
    updated_prop.write_bytes(updated)

    image = work / 'system.img'
    shutil.copyfile(baseline, image)
    assert sha(image) == EXPECTED_RAW_SHA
    run([HOST / 'avbtool', 'erase_footer', '--image', image], capture_output=True)
    assert image.stat().st_size == system_descriptor.image_size
    inode_after = bytearray(inode_before)
    struct.pack_into('<I', inode_after, 4, len(updated))
    struct.pack_into('<I', inode_after, 108, len(updated) >> 32)
    with image.open('r+b') as target:
        for logical, block in enumerate(blocks):
            start = logical * block_size
            chunk = updated[start:start + block_size]
            if chunk:
                target.seek(block * block_size)
                target.write(chunk)
        target.seek(inode_offset)
        target.write(inode_after)
    differences = changed_blocks(baseline, image, system_descriptor.image_size, block_size)
    permitted = set(blocks) | {inode_offset // block_size}
    assert set(differences) <= permitted and inode_offset // block_size in differences
    with baseline.open('rb') as a, image.open('rb') as b:
        inode_block = inode_offset // block_size * block_size
        a.seek(inode_block); b.seek(inode_block)
        old_block, new_block = a.read(block_size), b.read(block_size)
        expected = bytearray(old_block)
        offset = inode_offset % block_size
        expected[offset:offset + inode_size] = inode_after
        assert bytes(expected) == new_block, 'Other inode metadata changed'
    readback = work / 'readback-build.prop'
    debugfs(image, f'dump {PROP_PATH} {readback}')
    assert readback.read_bytes() == updated
    stat_after = debugfs(image, f'stat {PROP_PATH}')
    assert stat_before.replace(f'Size: {old_size}', f'Size: {len(updated)}', 1) == stat_after
    assert xattrs_before == debugfs(image, f'ea_list {PROP_PATH}')
    assert blocks == list(map(int, debugfs(image, f'blocks {PROP_PATH}').split()))
    fsck = run(['e2fsck', '-fn', image], capture_output=True, text=True)
    (work / 'e2fsck-readonly.txt').write_text(fsck.stdout + fsck.stderr)

    command = [HOST / 'avbtool', 'add_hashtree_footer', '--image', image,
               '--partition_size', EXPECTED_RAW_BYTES, '--partition_name', 'system',
               '--hash_algorithm', system_descriptor.hash_algorithm,
               '--salt', system_descriptor.salt.hex(), '--block_size', block_size,
               '--fec_num_roots', system_descriptor.fec_num_roots,
               '--algorithm', 'NONE', '--rollback_index', old_image_header.rollback_index,
               '--rollback_index_location', old_image_header.rollback_index_location,
               '--flags', old_image_header.flags]
    for descriptor in image_descriptors:
        if isinstance(descriptor, avbtool.AvbPropertyDescriptor):
            key = descriptor.key.decode() if isinstance(descriptor.key, bytes) else descriptor.key
            value = descriptor.value.decode() if isinstance(descriptor.value, bytes) else descriptor.value
            command += ['--prop', key + ':' + value]
        else:
            assert descriptor is system_descriptor, 'Unexpected embedded AVB descriptor'
    run(command, capture_output=True)
    assert image.stat().st_size == EXPECTED_RAW_BYTES
    run([HOST / 'avbtool', 'verify_image', '--image', image], capture_output=True)
    _, new_image_header, new_image_descriptors, _ = parse_image(avb, avbtool, image)
    new_system = [d for d in new_image_descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == 'system']
    assert len(new_system) == 1
    updated_descriptor = new_system[0]
    assert updated_descriptor.root_digest != system_descriptor.root_digest
    for field in ('flags', 'rollback_index', 'rollback_index_location', 'algorithm_type',
                  'required_libavb_version_major', 'required_libavb_version_minor', 'release_string'):
        assert getattr(old_image_header, field) == getattr(new_image_header, field), field
    assert [d.encode() for d in image_descriptors if not isinstance(d, avbtool.AvbHashtreeDescriptor)] == [
        d.encode() for d in new_image_descriptors if not isinstance(d, avbtool.AvbHashtreeDescriptor)]
    for field in ('dm_verity_version', 'image_size', 'tree_offset', 'tree_size', 'data_block_size',
                  'hash_block_size', 'fec_num_roots', 'fec_offset', 'fec_size', 'hash_algorithm',
                  'partition_name', 'salt', 'flags'):
        assert getattr(system_descriptor, field) == getattr(updated_descriptor, field), field

    descriptors = [updated_descriptor if descriptor is old_chain_system[0] else descriptor
                   for descriptor in chain_descriptors]
    blob = avb._generate_vbmeta_blob(algorithm_name='SHA256_RSA2048',
        key_path=str(ROM / 'external/avb/test/data/testkey_rsa2048.pem'),
        public_key_metadata_path=None, descriptors=descriptors, chain_partitions_use_ab=None,
        chain_partitions_do_not_use_ab=None, rollback_index=old_chain_header.rollback_index,
        flags=old_chain_header.flags, rollback_index_location=old_chain_header.rollback_index_location,
        props=None, props_from_file=None, kernel_cmdlines=None, setup_rootfs_from_kernel=None,
        ht_desc_to_setup=None, include_descriptors_from_image=None, signing_helper=None,
        signing_helper_with_files=None, release_string=old_chain_header.release_string,
        append_to_release_string=None, required_libavb_version_minor=old_chain_header.required_libavb_version_minor)
    vbmeta = work / 'vbmeta_system.img'
    assert len(blob) <= base_vbmeta.stat().st_size
    vbmeta.write_bytes(blob + b'\0' * (base_vbmeta.stat().st_size - len(blob)))
    _, new_chain_header, new_chain_descriptors, _ = parse_image(avb, avbtool, vbmeta)
    assert avbtool.verify_vbmeta_signature(new_chain_header, blob)
    for field in ('flags', 'rollback_index', 'rollback_index_location', 'algorithm_type',
                  'required_libavb_version_major', 'required_libavb_version_minor', 'release_string'):
        assert getattr(old_chain_header, field) == getattr(new_chain_header, field), field
    assert len(chain_descriptors) == len(new_chain_descriptors)
    assert sum(a.encode() != b.encode() for a, b in zip(chain_descriptors, new_chain_descriptors)) == 1
    for a, b in zip(chain_descriptors, new_chain_descriptors):
        if a.encode() != b.encode():
            assert a is old_chain_system[0] and b.encode() == updated_descriptor.encode()
    # Signing with the existing development key must preserve its encoded public key.
    def public_key(path, header, image_offset=0):
        with path.open('rb') as stream:
            stream.seek(image_offset + 256 + header.authentication_data_block_size + header.public_key_offset)
            return stream.read(header.public_key_size)
    assert public_key(base_vbmeta, old_chain_header) == public_key(vbmeta, new_chain_header)
    assert sha(baseline) == EXPECTED_RAW_SHA and sha(base_vbmeta) == EXPECTED_VBMETA_SHA
    # Recheck filesystem bytes after AVB recreation, which must only append data.
    assert changed_blocks(baseline, image, system_descriptor.image_size, block_size) == differences

    destination.mkdir()
    files = []
    for partition, source in (('system', image), ('vbmeta_system', vbmeta)):
        output = destination / (partition + '.img')
        shutil.copyfile(source, output)
        assert sha(output) == sha(source)
        files.append(dict(partition=partition, name=output.name, bytes=output.stat().st_size, sha256=sha(output)))
    report = dict(prerequisites, files=files, compiled_build_prop=str(compiled_prop),
                  compiled_build_prop_sha256=sha(compiled_prop), changed_system_files=[PROP_PATH],
                  changed_property='ro.product.model', model=TARGET_MODEL.decode(),
                  original_build_prop_sha256=sha(original_prop), updated_build_prop_sha256=sha(updated_prop),
                  updated_build_prop_bytes=len(updated), filesystem_changed_blocks=differences,
                  changed_inode_fields=['i_size_lo'],
                  original_inode_sha256=hashlib.sha256(inode_before).hexdigest(),
                  updated_inode_sha256=hashlib.sha256(inode_after).hexdigest(),
                  build_prop_inode_number_preserved=True, build_prop_allocated_blocks_preserved=True,
                  build_prop_mode_owner_group_times_and_all_xattrs_preserved=True,
                  all_other_files_and_inode_bytes_preserved=True,
                  exact_system_base_verified=True, filesystem_readback_verified=True,
                  readonly_e2fsck_passed=True, partition_sizes_unchanged=True,
                  system_hashtree_verified=True, signatures_verified=True,
                  only_system_avb_descriptor_changed=True, other_avb_descriptors_and_header_preserved=True,
                  vendor_odm_and_vbmeta_untouched=True, runtime_verified=False)
    (destination / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    (destination / 'SHA256SUMS').write_text(''.join(f['sha256'] + '  ' + f['name'] + '\n' for f in files))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
