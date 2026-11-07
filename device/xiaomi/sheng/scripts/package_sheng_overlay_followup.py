#!/usr/bin/env python3
"""Package explicitly scoped device-built overlays over verified installations.

Only development image copies are changed. Normal builds install these same
device_specific overlays through device.mk; public source remains read-only.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import uuid

from audit_erofs_metadata import metadata
from package_sheng_location_followup import allocated_inodes, debugfs
from package_sheng_model_followup import sha, run, parse_image, changed_blocks, ROM, HOST, PRODUCT

DEVICE = Path(__file__).resolve().parents[1]
ODM_BYTES = 1141067776
VBMETA_BYTES = 8192
SYSTEM_BYTES = 1005133824
VBMETA_SYSTEM_BYTES = 4096
SYSTEM_DEFAULTS_PATH = '/system/etc/device-config-defaults'
SYSTEM_DEFAULTS_BYTES = b'window_manager:ignore_activity_orientation_request=enabled\n'
BASELINES = {
    10: {
        'odm_release': 'r5',
        'odm_sha256': '9735c4f6aa8dcc1f3b327b54ebc47f16b4c697e26095f7530d4671dfda3aac4d',
        'vbmeta_release': 'r6',
        'vbmeta_sha256': '488757df791a7cdf9387e2b81b30fbddb2210a6a0ccdf338048dc8f0c75e33af',
        'overlays': ('FrameworkResOverlaySheng', 'SystemUIResOverlaySheng'),
    },
    11: {
        'odm_release': 'r10',
        'odm_sha256': '35ceeb371eedb76f4d268ae5a65387f2353150e6b86a84366039821aa69b4d0c',
        'vbmeta_release': 'r10',
        'vbmeta_sha256': '5e3c933a430680a1b150607580c2f711166992b6c0fb9520a8c5ecc6edf0f312',
        'overlays': ('SystemUIResOverlaySheng',),
    },
    12: {
        'odm_release': 'r11',
        'odm_sha256': 'd947ae93faad87bcb26da93afe245d6528e04f2b698ca4116257d29262ff5aac',
        'vbmeta_release': 'r11',
        'vbmeta_sha256': '43412dea1eebb58489cd8acfec9368123af94090d3b2665aab225abc61f17e78',
        'overlays': ('FrameworkResOverlaySheng',),
        'add_system_defaults': True,
    },
}
INHERITED = {
    'system_ext': ('r9', '7a4e2a739f9cbc3a9713113e40f8a181dde34875c1ef0abee5e53411de58c573'),
    'vbmeta_system': ('r9', 'c0a925d91b33750a09eea0b99beeb759a37c47ac8736112c802a8adbf68eb0f8'),
    'system': ('r7', '50cb7ebad3703ca03734f566aa6ea1f462675f4b361c968849b913b33e932089'),
    'vendor': ('r6', 'c663a57f003d3cd0791ec2a7b50ad36ed1e1d1d96c0b4b414adc5b3bc63ef038'),
}


def contents(root):
    return {str(p.relative_to(root)): ('link', os.readlink(p)) if p.is_symlink()
            else ('file', sha(p)) for p in root.rglob('*')
            if p.is_file() or p.is_symlink()}


def certificates(path):
    result = run([ROM / 'prebuilts/jdk/jdk21/linux-x86/bin/java', '-jar',
                  ROM / 'prebuilts/sdk/tools/linux/lib/apksigner.jar',
                  'verify', '--print-certs', path], capture_output=True, text=True)
    digests = sorted(line.split(':', 1)[1].strip() for line in result.stdout.splitlines()
                     if 'certificate SHA-256 digest:' in line)
    assert digests, 'No verified overlay signing certificate'
    return digests


def complete_metadata(image):
    """Add timestamps, inode types and link counts to the existing xattr audit."""
    result = metadata(image)
    with Path(image).open('rb') as stream:
        def read(offset, amount):
            stream.seek(offset)
            value = stream.read(amount)
            assert len(value) == amount
            return value
        sb = read(1024, 128)
        block = 1 << sb[12]
        root_nid = struct.unpack_from('<H', sb, 14)[0]
        meta_block = struct.unpack_from('<I', sb, 40)[0]
        build_seconds, build_ns = struct.unpack_from('<QI', sb, 24)

        def walk(nid, path):
            offset = meta_block * block + nid * 32
            header = read(offset, 64)
            format_, count, mode = struct.unpack_from('<HHH', header)
            extended = format_ & 1
            length = 64 if extended else 32
            size = struct.unpack_from('<Q' if extended else '<I', header, 8)[0]
            data_block = struct.unpack_from('<I', header, 16)[0]
            xsize = 12 + (count - 1) * 4 if count else 0
            seconds = struct.unpack_from('<Q', header, 32)[0] if extended else build_seconds
            nanoseconds = struct.unpack_from('<I', header, 40)[0] if extended else build_ns
            links = struct.unpack_from('<I', header, 44)[0] if extended else struct.unpack_from('<H', header, 6)[0]
            result[path].update(type=stat.S_IFMT(mode), mtime_ns=seconds * 1000000000 + nanoseconds,
                                nlink=links)
            if not stat.S_ISDIR(mode):
                return
            layout = (format_ >> 1) & 7
            assert layout in (0, 2), 'Unsupported compressed EROFS directory'
            for index in range((size + block - 1) // block):
                amount = min(block, size - index * block)
                where = offset + length + xsize if layout == 2 and amount < block else (data_block + index) * block
                data = read(where, amount)
                first_name = struct.unpack_from('<H', data, 8)[0]
                assert first_name % 12 == 0
                entries = [struct.unpack_from('<QHBB', data, i * 12) for i in range(first_name // 12)]
                for i, (child, start, _, _) in enumerate(entries):
                    end = entries[i + 1][1] if i + 1 < len(entries) else len(data)
                    name = data[start:end].rstrip(b'\0').decode()
                    if name not in ('.', '..'):
                        walk(child, path + '/' + name)
        walk(root_nid, '')
    return result, str(uuid.UUID(bytes=sb[48:64]))


def public_key(path, footer, header):
    start = (footer.vbmeta_offset if footer else 0) + header.SIZE + header.authentication_data_block_size
    with Path(path).open('rb') as stream:
        stream.seek(start + header.public_key_offset)
        key = stream.read(header.public_key_size)
    assert len(key) == header.public_key_size
    return key


def replace_chain_hashtree(avb, avbtool, chain, image_descriptor, target, algorithm):
    """Sign one changed descriptor while preserving the installed parent chain."""
    footer, header, old_chain, _ = parse_image(avb, avbtool, chain)
    assert header.algorithm_type == avbtool.ALGORITHMS[algorithm].algorithm_type
    assert header.public_key_metadata_size == 0
    selected = [d for d in old_chain if isinstance(d, avbtool.AvbHashtreeDescriptor)
                and d.partition_name == image_descriptor.partition_name]
    assert len(selected) == 1 and selected[0].encode() != image_descriptor.encode()
    descriptors = [image_descriptor if d is selected[0] else d for d in old_chain]
    key_bits = {'SHA256_RSA2048': 2048, 'SHA256_RSA4096': 4096}[algorithm]
    blob = avb._generate_vbmeta_blob(algorithm_name=algorithm,
        key_path=str(ROM / f'external/avb/test/data/testkey_rsa{key_bits}.pem'),
        public_key_metadata_path=None, descriptors=descriptors, chain_partitions_use_ab=None,
        chain_partitions_do_not_use_ab=None, rollback_index=header.rollback_index, flags=header.flags,
        rollback_index_location=header.rollback_index_location, props=None, props_from_file=None,
        kernel_cmdlines=None, setup_rootfs_from_kernel=None, ht_desc_to_setup=None,
        include_descriptors_from_image=None, signing_helper=None, signing_helper_with_files=None,
        release_string=header.release_string, append_to_release_string=None,
        required_libavb_version_minor=header.required_libavb_version_minor)
    assert len(blob) <= chain.stat().st_size
    target.write_bytes(blob + b'\0' * (chain.stat().st_size - len(blob)))
    new_footer, new_header, new_chain, _ = parse_image(avb, avbtool, target)
    assert avbtool.verify_vbmeta_signature(new_header, blob)
    assert public_key(chain, footer, header) == public_key(target, new_footer, new_header)
    for field in ('flags', 'rollback_index', 'rollback_index_location', 'algorithm_type',
                  'required_libavb_version_major', 'required_libavb_version_minor', 'release_string'):
        assert getattr(new_header, field) == getattr(header, field), field
    assert len(old_chain) == len(new_chain)
    changed = [(a, b) for a, b in zip(old_chain, new_chain) if a.encode() != b.encode()]
    assert len(changed) == 1 and changed[0][0] is selected[0]
    assert changed[0][1].encode() == image_descriptor.encode()


def ext4_snapshot(image):
    """Read existing inodes, external xattrs and every sparse-super copy."""
    inodes = allocated_inodes(image)
    with Path(image).open('rb') as stream:
        def read(offset, amount):
            stream.seek(offset)
            value = stream.read(amount)
            assert len(value) == amount
            return value
        sb = read(1024, 1024)
        assert struct.unpack_from('<I', sb, 92)[0] & 4 == 0, 'Journal allocation is outside this delta'
        assert struct.unpack_from('<I', sb, 96)[0] & (0x10 | 0x80) == 0, 'meta_bg/64bit unsupported'
        assert struct.unpack_from('<I', sb, 100)[0] & 0x400 == 0, 'metadata_csum unsupported'
        block = 1024 << struct.unpack_from('<I', sb, 24)[0]
        count = struct.unpack_from('<I', sb, 4)[0]
        per_group = struct.unpack_from('<I', sb, 32)[0]
        inodes_per_group = struct.unpack_from('<I', sb, 40)[0]
        group_count = (count + per_group - 1) // per_group
        assert block == 4096 and struct.unpack_from('<I', sb, 20)[0] == 0
        descriptor_data = read(block, group_count * 32)
        groups = [struct.unpack_from('<III', descriptor_data, group * 32)
                  for group in range(group_count)]
        sparse = bool(struct.unpack_from('<I', sb, 100)[0] & 1)
        def power(number, base):
            while number > 1 and number % base == 0:
                number //= base
            return number == 1
        supers = {1024: sb}
        for group in range(1, group_count):
            if not sparse or group == 1 or any(power(group, base) for base in (3, 5, 7)):
                offset = group * per_group * block
                backup = read(offset, 1024)
                assert struct.unpack_from('<H', backup, 56)[0] == 0xEF53
                supers[offset] = backup
        external = {}
        for inode in inodes.values():
            assert struct.unpack_from('<H', inode, 118)[0] == 0, 'High external-xattr address unsupported'
            acl = struct.unpack_from('<I', inode, 104)[0]
            if acl:
                external[acl] = read(acl * block, block)
                assert struct.unpack_from('<I', external[acl])[0] == 0xEA020000
    descriptor_blocks = (group_count * 32 + block - 1) // block
    metadata_blocks = {offset // block for offset in supers}
    for super_block in list(metadata_blocks):
        metadata_blocks.update(range(super_block + 1, super_block + 1 + descriptor_blocks))
    return dict(inodes=inodes, external_xattrs=external, supers=supers, block_size=block,
                groups=groups, inodes_per_group=inodes_per_group, blocks_per_group=per_group,
                allocation_metadata_blocks=metadata_blocks)


def preserve_ext4_super_metadata(image, before):
    """Retain allocation counters, restoring only offline write accounting/time."""
    current = ext4_snapshot(image)
    assert current['supers'].keys() == before['supers'].keys()
    with Path(image).open('r+b') as stream:
        for offset, old in before['supers'].items():
            new = current['supers'][offset]
            # debugfs legitimately updates free counters and write accounting.
            # Every other byte must already match the original superblock copy.
            masked = bytearray(new)
            for start, end in ((12, 20), (48, 52), (376, 384)):
                masked[start:end] = old[start:end]
            assert masked == old, f'Unrelated ext4 superblock metadata changed: {offset}'
            assert struct.unpack_from('<I', new, 12)[0] + 1 == struct.unpack_from('<I', old, 12)[0]
            assert struct.unpack_from('<I', new, 16)[0] + 1 == struct.unpack_from('<I', old, 16)[0]
            for start, end in ((48, 52), (376, 384)):
                stream.seek(offset + start)
                stream.write(old[start:end])
    final = ext4_snapshot(image)
    for offset, old in before['supers'].items():
        expected = bytearray(old)
        expected[12:20] = current['supers'][offset][12:20]
        assert final['supers'][offset] == expected
    return final


def add_system_defaults(workspace, work, avb, avbtool):
    """Add one compiled file without rebuilding or altering existing ext4 nodes."""
    system_release, system_sha = INHERITED['system']
    chain_release, chain_sha = INHERITED['vbmeta_system']
    base = workspace / f'artifacts/system-hardware-followup-sheng-{system_release}/system.img'
    chain = workspace / f'artifacts/system-hardware-followup-sheng-{chain_release}/vbmeta_system.img'
    assert base.stat().st_size == SYSTEM_BYTES and sha(base) == system_sha
    assert chain.stat().st_size == VBMETA_SYSTEM_BYTES and sha(chain) == chain_sha
    source = PRODUCT / 'system/etc/device-config-defaults'
    tree_source = DEVICE / 'configs/device-config-defaults'
    assert source.read_bytes() == tree_source.read_bytes() == SYSTEM_DEFAULTS_BYTES
    assert not re.search(r'\s', str(source)), 'debugfs source path must have no whitespace'
    footer, old_header, descriptors, _ = parse_image(avb, avbtool, base)
    _, chain_header, chain_descriptors, _ = parse_image(avb, avbtool, chain)
    selected = [d for d in descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)
                and d.partition_name == 'system']
    old_chain_system = [d for d in chain_descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)
                        and d.partition_name == 'system']
    assert len(selected) == len(old_chain_system) == 1
    tree = selected[0]
    assert tree.encode() == old_chain_system[0].encode()
    assert footer and footer.original_image_size == tree.image_size
    assert old_header.algorithm_type == 0 and old_header.public_key_metadata_size == 0
    assert chain_header.algorithm_type == avbtool.ALGORITHMS['SHA256_RSA2048'].algorithm_type
    assert tree.data_block_size == tree.hash_block_size == 4096 and tree.fec_num_roots == 2 and tree.flags == 0
    old = ext4_snapshot(base)
    assert len(old['external_xattrs']) == 2, 'The pinned base has two existing external xattr blocks'
    before_root = work / 'system-before'
    before_root.mkdir()
    debugfs(base, f'rdump / {before_root}')
    before_files = contents(before_root)
    assert 'system/etc/device-config-defaults' not in before_files
    parent = debugfs(base, 'stat /system/etc')
    assert 'Type: directory' in parent and 'Size: 4096' in parent
    image = work / 'system.img'
    shutil.copyfile(base, image)
    run([HOST / 'avbtool', 'erase_footer', '--image', image], capture_output=True)
    assert image.stat().st_size == tree.image_size
    label = work / 'system-file-context'
    label.write_bytes(b'u:object_r:system_file:s0\0')
    commands = [f"set_current_time @{struct.unpack_from('<I', old['supers'][1024], 48)[0]}",
                f'write {source} {SYSTEM_DEFAULTS_PATH}',
                f'set_inode_field {SYSTEM_DEFAULTS_PATH} mode 0100644',
                f'ea_set -f {label} {SYSTEM_DEFAULTS_PATH} security.selinux']
    for field, value in (('uid', '0'), ('gid', '0'), ('atime', '@1230768000'),
                         ('mtime', '@1230768000'), ('ctime', '@1230768000'), ('crtime', '@1230768000')):
        commands.append(f'set_inode_field {SYSTEM_DEFAULTS_PATH} {field} {value}')
    command_file = work / 'add-system-defaults.debugfs'
    command_file.write_text('\n'.join(commands) + '\n')
    result = run(['debugfs', '-w', '-f', command_file, image], capture_output=True, text=True)
    (work / 'add-system-defaults.log').write_text(result.stdout + result.stderr)
    assert not any(message in result.stderr.lower() for message in
                   ('not found', 'not open', 'already exists', 'could not', 'usage:',
                    'no free', 'not enough', 'unknown request', 'command not found'))
    after = preserve_ext4_super_metadata(image, old)
    assert old['inodes'].keys() <= after['inodes'].keys()
    assert all(after['inodes'][number] == inode for number, inode in old['inodes'].items()), 'Existing system inode bytes changed'
    assert after['external_xattrs'] == old['external_xattrs'], 'Existing external xattrs or reference counts changed'
    stat_result = debugfs(image, f'stat {SYSTEM_DEFAULTS_PATH}')
    number = int(re.search(r'Inode:\s*(\d+)', stat_result)[1])
    assert after['inodes'].keys() - old['inodes'].keys() == {number}
    inode = after['inodes'][number]
    assert struct.unpack_from('<H', inode, 0)[0] == 0o100644
    assert all(struct.unpack_from('<H', inode, offset)[0] == 0 for offset in (2, 24, 120, 122))
    assert struct.unpack_from('<I', inode, 4)[0] == len(SYSTEM_DEFAULTS_BYTES)
    assert struct.unpack_from('<I', inode, 104)[0] == 0, 'New SELinux label must remain inline'
    for offset in (8, 12, 16, 144):
        assert struct.unpack_from('<I', inode, offset)[0] == 1230768000
    assert struct.unpack_from('<H', inode, 128)[0] == 32, 'Expected 32-byte extra inode fields'
    assert struct.unpack_from('<H', inode, 130)[0] == 0, 'No metadata checksum is enabled'
    for offset in (132, 136, 140, 148):
        assert struct.unpack_from('<I', inode, offset)[0] == 0
    actual_label = work / 'system-new-file-label'
    debugfs(image, f'ea_get -f {actual_label} {SYSTEM_DEFAULTS_PATH} security.selinux')
    assert actual_label.read_bytes() == label.read_bytes()
    fsck = run(['e2fsck', '-fn', image], capture_output=True, text=True)
    (work / 'system-e2fsck-readonly.txt').write_text(fsck.stdout + fsck.stderr)
    after_root = work / 'system-after'
    after_root.mkdir()
    debugfs(image, f'rdump / {after_root}')
    after_files = contents(after_root)
    assert {p for p in before_files.keys() | after_files.keys() if before_files.get(p) != after_files.get(p)} == {'system/etc/device-config-defaults'}
    assert (after_root / 'system/etc/device-config-defaults').read_bytes() == SYSTEM_DEFAULTS_BYTES
    fs_changes = changed_blocks(base, image, tree.image_size, tree.data_block_size)
    new_data_blocks = list(map(int, debugfs(image, f'blocks {SYSTEM_DEFAULTS_PATH}').split()))
    parent_blocks = list(map(int, debugfs(base, 'blocks /system/etc').split()))
    assert len(new_data_blocks) == len(parent_blocks) == 1, 'Exactly one file block and one existing directory block'
    inode_group, inode_index = divmod(number - 1, old['inodes_per_group'])
    _, inode_bitmap, inode_table = old['groups'][inode_group]
    permitted_blocks = old['allocation_metadata_blocks'] | set(parent_blocks) | set(new_data_blocks)
    permitted_blocks |= {inode_bitmap, inode_table + inode_index * 256 // old['block_size']}
    for data_block in new_data_blocks:
        data_group = data_block // old['blocks_per_group']
        permitted_blocks.add(old['groups'][data_group][0])
    assert set(fs_changes) <= permitted_blocks, 'Unrelated ext4 filesystem block changed'
    command = [HOST / 'avbtool', 'add_hashtree_footer', '--image', image,
               '--partition_size', SYSTEM_BYTES, '--partition_name', 'system',
               '--hash_algorithm', tree.hash_algorithm, '--salt', tree.salt.hex(),
               '--block_size', tree.data_block_size, '--fec_num_roots', tree.fec_num_roots,
               '--algorithm', 'NONE', '--rollback_index', old_header.rollback_index,
               '--rollback_index_location', old_header.rollback_index_location, '--flags', old_header.flags]
    for descriptor in descriptors:
        if isinstance(descriptor, avbtool.AvbPropertyDescriptor):
            command += ['--prop', descriptor.key + ':' + descriptor.value.decode('utf-8')]
        else:
            assert descriptor is tree
    run(command, capture_output=True)
    assert image.stat().st_size == SYSTEM_BYTES
    run([HOST / 'avbtool', 'verify_image', '--image', image], capture_output=True)
    _, new_header, new_descriptors, _ = parse_image(avb, avbtool, image)
    replacement = [d for d in new_descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)
                   and d.partition_name == 'system']
    assert len(replacement) == 1 and replacement[0].root_digest != tree.root_digest
    for field in ('flags', 'rollback_index', 'rollback_index_location', 'algorithm_type',
                  'required_libavb_version_major', 'required_libavb_version_minor', 'release_string'):
        assert getattr(new_header, field) == getattr(old_header, field), field
    for field in ('dm_verity_version', 'image_size', 'tree_offset', 'tree_size', 'data_block_size',
                  'hash_block_size', 'fec_num_roots', 'fec_offset', 'fec_size', 'hash_algorithm', 'salt', 'flags'):
        assert getattr(replacement[0], field) == getattr(tree, field), field
    assert [d.encode() for d in new_descriptors if not isinstance(d, avbtool.AvbHashtreeDescriptor)] == [
        d.encode() for d in descriptors if not isinstance(d, avbtool.AvbHashtreeDescriptor)]
    vbmeta_system = work / 'vbmeta_system.img'
    replace_chain_hashtree(avb, avbtool, chain, replacement[0], vbmeta_system, 'SHA256_RSA2048')
    assert changed_blocks(base, image, tree.image_size, tree.data_block_size) == fs_changes
    assert sha(base) == system_sha and sha(chain) == chain_sha
    report = dict(system_base_sha256=system_sha, system_base_bytes=SYSTEM_BYTES,
        vbmeta_system_base_sha256=chain_sha, vbmeta_system_base_bytes=VBMETA_SYSTEM_BYTES,
        changed_system_files=['etc/device-config-defaults'],
        system_compiled_inputs={'etc/device-config-defaults': sha(source)},
        system_new_inode_number=number, system_external_xattr_block_numbers=sorted(old['external_xattrs']),
        system_filesystem_changed_blocks=fs_changes,
        system_permitted_filesystem_changed_blocks=sorted(permitted_blocks),
        system_filesystem_changed_blocks_within_scope=True,
        all_existing_system_inode_bytes_preserved=True, system_external_xattr_blocks_preserved=True,
        system_superblock_metadata_preserved=True, system_new_file_metadata_verified=True,
        system_filesystem_readback_verified=True, readonly_e2fsck_passed=True,
        system_hashtree_verified=True, only_system_avb_descriptor_changed=True,
        system_avb_public_key_preserved=True, system_avb_headers_and_properties_preserved=True)
    return [('system', image), ('vbmeta_system', vbmeta_system)], report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--revision', type=int, choices=sorted(BASELINES), default=11)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    assert args.revision in BASELINES, 'No verified baseline for this revision'
    baseline = BASELINES[args.revision]
    odm_sha, vbmeta_sha = baseline['odm_sha256'], baseline['vbmeta_sha256']
    base = workspace / f"artifacts/system-hardware-followup-sheng-{baseline['odm_release']}/odm.img"
    chain = workspace / f"artifacts/system-hardware-followup-sheng-{baseline['vbmeta_release']}/vbmeta.img"
    assert base.stat().st_size == ODM_BYTES and sha(base) == odm_sha
    assert chain.stat().st_size == VBMETA_BYTES and sha(chain) == vbmeta_sha
    for partition, (release, digest) in INHERITED.items():
        path = workspace / f'artifacts/system-hardware-followup-sheng-{release}/{partition}.img'
        assert sha(path) == digest, f'Inherited {partition} image mismatch'
    destination = workspace / f'artifacts/system-hardware-followup-sheng-r{args.revision}'
    assert not destination.exists(), 'Never overwrite a built/flashed revision'
    changes = {f'overlay/{name}.apk': PRODUCT / f'odm/overlay/{name}.apk' for name in baseline['overlays']}
    for source in changes.values():
        assert source.is_file(), source
    work = Path('/root/sheng-lineage/hardware-followup') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-overlay')
    work.mkdir(parents=True)
    root = work / 'odm'
    run([HOST / 'fsck.erofs', '-d0', '--extract=' + str(root), '--preserve', base],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    before = contents(root)
    old_metadata, old_uuid = complete_metadata(base)
    signer_digests = {}
    for relative, source in changes.items():
        target = root / relative
        assert target.is_file() and not target.is_symlink(), relative
        old_certs = certificates(target)
        assert certificates(source) == old_certs, f'Overlay certificate changed: {relative}'
        signer_digests[relative] = old_certs
        shutil.copyfile(source, target)
    # fsck preserves ownership/modes where available; restore every recorded
    # mtime explicitly, including symlinks and directories, after changing APKs.
    for relative, inode in old_metadata.items():
        target = root / relative.lstrip('/')
        os.utime(target, ns=(inode['mtime_ns'], inode['mtime_ns']), follow_symlinks=False)
    after = contents(root)
    changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
    assert changed == set(changes), f'Unexpected ODM delta: {sorted(changed)}'
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    footer, image_header, embedded_before, _ = parse_image(avb, avbtool, base)
    chain_footer, header, old_chain, _ = parse_image(avb, avbtool, chain)
    old_odm = [d for d in embedded_before if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == 'odm']
    chain_odm = [d for d in old_chain if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == 'odm']
    assert len(old_odm) == len(chain_odm) == 1 and old_odm[0].encode() == chain_odm[0].encode()
    assert footer and image_header.algorithm_type == 0
    assert image_header.public_key_metadata_size == header.public_key_metadata_size == 0
    assert old_odm[0].flags == 0 and old_odm[0].hash_algorithm == 'sha256'
    assert header.algorithm_type == avbtool.ALGORITHMS['SHA256_RSA4096'].algorithm_type
    config = work / 'odm_filesystem_config.txt'
    entries = []
    for relative, inode in sorted(old_metadata.items()):
        capability = 0
        raw = inode['xattrs'].get('6:capability')
        if raw:
            fields = struct.unpack('<5I', bytes.fromhex(raw))
            assert fields[0] == 0x02000001 and fields[2] == fields[4] == 0
            capability = fields[1] | (fields[3] << 32)
        name = 'odm' + relative if relative else ''
        entries.append(f"{name} {inode['uid']} {inode['gid']} {inode['mode']:o} capabilities=0x{capability:x}")
    config.write_text('\n'.join(entries) + '\n')
    contexts = ROM / 'out/soong/.intermediates/system/sepolicy/file_contexts.concat.tmp/android_common/gen/file_contexts.concat.tmp'
    run([HOST / 'sefcontext_compile', '-o', work / 'file_contexts.bin', contexts])
    props = dict(line.split('=', 1) for line in
                 (PRODUCT / 'obj/PACKAGING/odm_intermediates/odm_image_info.txt').read_text().splitlines()
                 if '=' in line)
    footer_arguments = ['--hash_algorithm', old_odm[0].hash_algorithm, '--salt', old_odm[0].salt.hex()]
    for descriptor in embedded_before:
        if isinstance(descriptor, avbtool.AvbPropertyDescriptor):
            footer_arguments += ['--prop', descriptor.key + ':' + descriptor.value.decode('utf-8')]
        else:
            assert isinstance(descriptor, avbtool.AvbHashtreeDescriptor), 'Unexpected embedded AVB descriptor'
    props.update(use_dynamic_partition_size='false', odm_size=str(ODM_BYTES),
                 fs_config=str(config), odm_selinux_fc=str(work / 'file_contexts.bin'), uuid=old_uuid,
                 avb_odm_add_hashtree_footer_args=shlex.join(footer_arguments))
    props.pop('timestamp', None)  # Preserve per-inode mtimes from the extraction.
    info = work / 'odm_image_info.txt'
    info.write_text('\n'.join(key + '=' + value for key, value in props.items()) + '\n')
    image = work / 'odm.img'
    with (work / 'odm-build.log').open('w') as log:
        # The entire extracted tree has already been checked against the base.
        # build_image's filter-copy step recreates directories without their
        # original mtimes, so build this complete audited tree directly.
        run([HOST / 'build_image', root, info, image, PRODUCT / 'system'],
            cwd=ROM, stdout=log, stderr=subprocess.STDOUT)
    assert image.stat().st_size == ODM_BYTES
    run([HOST / 'avbtool', 'verify_image', '--image', image], capture_output=True)
    readback = work / 'odm-readback'
    run([HOST / 'fsck.erofs', '-d0', '--extract=' + str(readback), '--preserve', image],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert contents(readback) == after, 'Filesystem content readback mismatch'
    new_metadata, new_uuid = complete_metadata(image)
    assert new_metadata == old_metadata, 'EROFS type/owners/modes/xattrs/links/timestamps changed'
    assert new_uuid == old_uuid, 'EROFS UUID changed'
    new_image_footer, new_image_header, embedded_after, _ = parse_image(avb, avbtool, image)
    updated = [d for d in embedded_after if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == 'odm']
    assert len(updated) == 1 and len(embedded_before) == len(embedded_after)
    assert new_image_footer and new_image_header.public_key_metadata_size == 0
    for field in ('flags', 'rollback_index', 'rollback_index_location', 'algorithm_type',
                  'required_libavb_version_major', 'required_libavb_version_minor', 'release_string'):
        assert getattr(new_image_header, field) == getattr(image_header, field), field
    for field in ('dm_verity_version', 'data_block_size', 'hash_block_size',
                  'fec_num_roots', 'hash_algorithm', 'salt', 'flags'):
        assert getattr(updated[0], field) == getattr(old_odm[0], field), field
    for old, new in zip(embedded_before, embedded_after):
        if not isinstance(old, avbtool.AvbHashtreeDescriptor):
            assert old.encode() == new.encode(), 'Embedded AVB property changed'
    vbmeta = work / 'vbmeta.img'
    replace_chain_hashtree(avb, avbtool, chain, updated[0], vbmeta, 'SHA256_RSA4096')
    outputs = [('odm', image), ('vbmeta', vbmeta)]
    system_report = {}
    if baseline.get('add_system_defaults'):
        system_outputs, system_report = add_system_defaults(workspace, work, avb, avbtool)
        outputs = system_outputs + outputs
    # No release output is published until both filesystem/AVB stages pass.
    assert sha(base) == odm_sha and sha(chain) == vbmeta_sha
    destination.mkdir()
    files = []
    for partition, path in outputs:
        target = destination / (partition + '.img')
        shutil.copyfile(path, target)
        assert sha(target) == sha(path)
        files.append(dict(partition=partition, name=target.name, bytes=path.stat().st_size, sha256=sha(path)))
    report = dict(revision=args.revision, files=files, work_dir=str(work),
        raw_base_sha256=odm_sha, raw_base_bytes=ODM_BYTES, vbmeta_base_sha256=vbmeta_sha,
        inherited_image_sha256={key: value[1] for key, value in INHERITED.items()},
        changed_odm_files=sorted(changed), compiled_inputs={key: sha(value) for key, value in changes.items()},
        overlay_signer_certificate_sha256=signer_digests,
        exact_installed_base_verified=True, filesystem_readback_verified=True,
        all_odm_inode_metadata_preserved=True, erofs_uuid_preserved=True,
        unrelated_files_preserved=True, partition_sizes_unchanged=True,
        odm_hashtree_verified=True, signatures_verified=True,
        only_odm_avb_descriptor_changed=True, embedded_avb_properties_preserved=True,
        overlay_certificates_preserved=True, existing_avb_public_key_preserved=True,
        r9_location_chain_preserved=True, hardware_boot_tested=False, runtime_verified=False)
    report.update(system_report)
    rendered = json.dumps(report, indent=2) + '\n'
    (destination / 'build-result.json').write_text(rendered)
    (destination / 'SHA256SUMS').write_text(''.join(f['sha256'] + '  ' + f['name'] + '\n' for f in files))
    (DEVICE / f'docs/system-hardware-followup-r{args.revision}.json').write_text(rendered)
    print(rendered)


if __name__ == '__main__':
    main()
