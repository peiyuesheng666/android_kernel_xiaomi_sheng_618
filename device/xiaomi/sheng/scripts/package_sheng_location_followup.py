#!/usr/bin/env python3
"""Add device-built location modules to the verified installed r7 AVB chain.

This development delta helper modifies copies of the r5 system_ext image only.
Normal builds install the same modules through device.mk. Inputs and public
source are read-only; nothing is flashed by this script.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys

from package_sheng_model_followup import sha, run, parse_image, ROM, HOST, PRODUCT

DEVICE = Path(__file__).resolve().parents[1]
RAW_SHA = 'b8436caaaa5cb1738c053afb3a77a4ea6135aeb1a07b774148ce17e3b16c60e9'
RAW_BYTES = 572813312
CHAIN_SHA = '5990b5c9fae89018ff9efb38ab338c48fc7c635f34fa95216a9f5a2c69fb212b'
SOURCES = {
    'priv-app/ShengMetokNLP/ShengMetokNLP.apk':
        PRODUCT / 'system_ext/priv-app/ShengMetokNLP/ShengMetokNLP.apk',
    'etc/permissions/privapp-permissions-sheng-location.xml':
        PRODUCT / 'system_ext/etc/permissions/privapp-permissions-sheng-location.xml',
    'overlay/ShengLocationOverlay/ShengLocationOverlay.apk':
        PRODUCT / 'system_ext/overlay/ShengLocationOverlay/ShengLocationOverlay.apk',
}


def debugfs(image, command, write=False):
    arguments = ['debugfs'] + (['-w'] if write else []) + ['-R', command, image]
    result = run(arguments, capture_output=True, text=True)
    if any(x in result.stderr for x in ('not found', 'not open', 'already exists',
                                       'Could not', 'Usage:', 'No free', 'not enough')):
        raise RuntimeError(result.stderr)
    return result.stdout


def files(root):
    return {str(p.relative_to(root)): ('link', os.readlink(p)) if p.is_symlink()
            else ('file', sha(p)) for p in root.rglob('*') if p.is_file() or p.is_symlink()}


def certificates(path):
    result = run([ROM / 'prebuilts/jdk/jdk21/linux-x86/bin/java', '-jar',
                  ROM / 'prebuilts/sdk/tools/linux/lib/apksigner.jar',
                  'verify', '--print-certs', path], capture_output=True, text=True)
    digests = sorted(line.split(':', 1)[1].strip() for line in result.stdout.splitlines()
                     if 'certificate SHA-256 digest:' in line)
    assert digests, 'APK has no verified certificate'
    return digests


def allocated_inodes(path):
    """Read allocated inode bytes, including xattr references, without stat cache."""
    result = {}
    with path.open('rb') as image:
        image.seek(1024)
        sb = image.read(1024)
        assert struct.unpack_from('<H', sb, 56)[0] == 0xEF53
        assert not (struct.unpack_from('<I', sb, 100)[0] & 0x400), 'metadata_csum unsupported'
        assert not (struct.unpack_from('<I', sb, 96)[0] & 0x80), '64-bit group descriptors unsupported'
        block = 1024 << struct.unpack_from('<I', sb, 24)[0]
        count, per_group = struct.unpack_from('<I', sb, 0)[0], struct.unpack_from('<I', sb, 40)[0]
        inode_size = struct.unpack_from('<H', sb, 88)[0]
        assert block == 4096 and inode_size == 256
        image.seek(block)
        descriptors = image.read(32 * ((count + per_group - 1) // per_group))
        for group in range((count + per_group - 1) // per_group):
            bitmap_block, table_block = struct.unpack_from('<II', descriptors, group * 32 + 4)
            image.seek(bitmap_block * block)
            bitmap = image.read(block)
            image.seek(table_block * block)
            table = image.read(per_group * inode_size)
            for index in range(min(per_group, count - group * per_group)):
                if bitmap[index // 8] & (1 << (index % 8)):
                    result[group * per_group + index + 1] = table[index * inode_size:(index + 1) * inode_size]
    return result


def certify_existing_inodes(before, after):
    assert before.keys() <= after.keys(), 'Existing inode removed'
    changed_directories = []
    for number, old in before.items():
        new = after[number]
        if old == new:
            continue
        assert stat.S_ISDIR(struct.unpack_from('<H', old, 0)[0]), f'Existing file inode changed: {number}'
        # Directory size, allocation and links may change when new entries are
        # added. Owners/mode/timestamps/flags/xattr references must be retained.
        for start, end in ((0, 4), (8, 26), (32, 40), (100, 108), (112, 256)):
            assert old[start:end] == new[start:end], f'Directory metadata changed: {number} [{start}:{end}]'
        changed_directories.append(number)
    return changed_directories


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw-base', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--revision', type=int, default=8)
    args = parser.parse_args()
    baseline, workspace = args.raw_base.resolve(), args.workspace.resolve()
    assert baseline.stat().st_size == RAW_BYTES and sha(baseline) == RAW_SHA
    chain = workspace / 'artifacts/system-hardware-followup-sheng-r7/vbmeta_system.img'
    assert sha(chain) == CHAIN_SHA, 'Must inherit r7 model-name system descriptor'
    destination = workspace / f'artifacts/system-hardware-followup-sheng-r{args.revision}'
    assert args.revision >= 8 and not destination.exists(), 'Never overwrite a release'
    for source in SOURCES.values():
        assert source.is_file(), source
    work = Path('/root/sheng-lineage/hardware-followup') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-location')
    work.mkdir(parents=True)
    stock_apk = DEVICE / 'location/proprietary/MetokNLP.apk'
    assert sha(stock_apk) == '846c84ea6468d3e3e6e71496ec3ac0fb91760ced00427e7c062e5da01384e8d3'
    assert sha(SOURCES['priv-app/ShengMetokNLP/ShengMetokNLP.apk']) == sha(stock_apk)
    assert certificates(stock_apk) == ['c9009d01ebf9f5d0302bc71b2fe9aa9a47a432bba17308a3111b75d7b2149025']
    system = workspace / 'artifacts/system-hardware-followup-sheng-r7/system.img'
    assert sha(system) == '50cb7ebad3703ca03734f566aa6ea1f462675f4b361c968849b913b33e932089'
    framework_apk = work / 'framework-res.apk'
    debugfs(system, f'dump /system/framework/framework-res.apk {framework_apk}')
    assert certificates(SOURCES['overlay/ShengLocationOverlay/ShengLocationOverlay.apk']) == certificates(framework_apk)
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    footer, image_header, image_descriptors, _ = parse_image(avb, avbtool, baseline)
    _, chain_header, old_chain, _ = parse_image(avb, avbtool, chain)
    selected = [d for d in image_descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == 'system_ext']
    chain_selected = [d for d in old_chain if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == 'system_ext']
    assert len(selected) == len(chain_selected) == 1 and selected[0].encode() == chain_selected[0].encode()
    descriptor = selected[0]
    assert footer and footer.original_image_size == descriptor.image_size
    assert image_header.algorithm_type == 0 and descriptor.flags == 0 and descriptor.fec_num_roots == 2
    assert image_header.public_key_metadata_size == chain_header.public_key_metadata_size == 0
    assert chain_header.algorithm_type == avbtool.ALGORITHMS['SHA256_RSA2048'].algorithm_type
    before_root = work / 'before'
    before_root.mkdir()
    debugfs(baseline, f'rdump / {before_root}')
    before_files = files(before_root)
    assert not set(SOURCES) & before_files.keys(), 'Location module already installed'
    old_inodes = allocated_inodes(baseline)
    assert all(struct.unpack_from('<I', inode, 104)[0] == 0 for inode in old_inodes.values()), 'External xattrs unsupported'
    image = work / 'system_ext.img'
    shutil.copyfile(baseline, image)
    run([HOST / 'avbtool', 'erase_footer', '--image', image], capture_output=True)
    context = work / 'system_file_context'
    context.write_bytes(b'u:object_r:system_file:s0\0')
    added = []
    created = set()
    for relative, source in SOURCES.items():
        current = before_root
        for parent in Path(relative).parts[:-1]:
            current = current / parent
            name = '/' + str(current.relative_to(before_root))
            if not current.is_dir() and name not in created:
                debugfs(image, f'mkdir {name}', write=True)
                debugfs(image, f'set_inode_field {name} mode 040755', write=True)
                debugfs(image, f'ea_set -f {context} {name} security.selinux', write=True)
                created.add(name)
        name = '/' + relative
        debugfs(image, f'write {source} {name}', write=True)
        debugfs(image, f'set_inode_field {name} mode 0100644', write=True)
        debugfs(image, f'ea_set -f {context} {name} security.selinux', write=True)
        added.append(name)
    # Set deterministic metadata on new nodes only; existing nodes are untouched.
    for name in sorted(created | set(added)):
        for field, value in (('uid', '0'), ('gid', '0'), ('atime', '1230768000'),
                             ('mtime', '1230768000'), ('ctime', '1230768000'), ('crtime', '1230768000')):
            debugfs(image, f'set_inode_field {name} {field} {value}', write=True)
    fsck = run(['e2fsck', '-fn', image], capture_output=True, text=True)
    (work / 'e2fsck-readonly.txt').write_text(fsck.stdout + fsck.stderr)
    new_inodes = allocated_inodes(image)
    directories = certify_existing_inodes(old_inodes, new_inodes)
    for name in sorted(created | set(added)):
        inode_number = int(re.search(r'Inode:\s*(\d+)', debugfs(image, f'stat {name}'))[1])
        inode = new_inodes[inode_number]
        assert struct.unpack_from('<H', inode, 0)[0] == (0o40755 if name in created else 0o100644)
        assert struct.unpack_from('<H', inode, 2)[0] == struct.unpack_from('<H', inode, 24)[0] == 0
        for offset in (8, 12, 16, 144):
            assert struct.unpack_from('<I', inode, offset)[0] == 1230768000, name
        labels = debugfs(image, f'ea_list {name}')
        assert 'u:object_r:system_file:s0' in labels and labels.count('security.selinux') == 1
    after_root = work / 'after'
    after_root.mkdir()
    debugfs(image, f'rdump / {after_root}')
    after_files = files(after_root)
    assert {k for k in before_files.keys() | after_files.keys() if before_files.get(k) != after_files.get(k)} == set(SOURCES)
    for relative, source in SOURCES.items():
        assert sha(after_root / relative) == sha(source)
        labels = debugfs(image, f'ea_list /{relative}')
        assert 'u:object_r:system_file:s0' in labels
    command = [HOST / 'avbtool', 'add_hashtree_footer', '--image', image,
               '--partition_size', RAW_BYTES, '--partition_name', 'system_ext',
               '--hash_algorithm', descriptor.hash_algorithm, '--salt', descriptor.salt.hex(),
               '--block_size', descriptor.data_block_size, '--fec_num_roots', descriptor.fec_num_roots,
               '--algorithm', 'NONE', '--rollback_index', image_header.rollback_index,
               '--rollback_index_location', image_header.rollback_index_location, '--flags', image_header.flags]
    for d in image_descriptors:
        if isinstance(d, avbtool.AvbPropertyDescriptor):
            key = d.key.decode() if isinstance(d.key, bytes) else d.key
            value = d.value.decode() if isinstance(d.value, bytes) else d.value
            command += ['--prop', key + ':' + value]
        else:
            assert d is descriptor
    run(command, capture_output=True)
    assert image.stat().st_size == RAW_BYTES
    run([HOST / 'avbtool', 'verify_image', '--image', image], capture_output=True)
    _, new_header, new_descriptors, _ = parse_image(avb, avbtool, image)
    replacement = [d for d in new_descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)]
    assert len(replacement) == 1 and replacement[0].partition_name == 'system_ext'
    assert replacement[0].root_digest != descriptor.root_digest
    assert [d.encode() for d in image_descriptors if not isinstance(d, avbtool.AvbHashtreeDescriptor)] == [
        d.encode() for d in new_descriptors if not isinstance(d, avbtool.AvbHashtreeDescriptor)]
    for field in ('dm_verity_version', 'image_size', 'tree_offset', 'tree_size', 'data_block_size',
                  'hash_block_size', 'fec_num_roots', 'fec_offset', 'fec_size', 'hash_algorithm', 'salt', 'flags'):
        assert getattr(descriptor, field) == getattr(replacement[0], field)
    descriptors = [replacement[0] if d is chain_selected[0] else d for d in old_chain]
    blob = avb._generate_vbmeta_blob(algorithm_name='SHA256_RSA2048',
        key_path=str(ROM / 'external/avb/test/data/testkey_rsa2048.pem'),
        public_key_metadata_path=None, descriptors=descriptors, chain_partitions_use_ab=None,
        chain_partitions_do_not_use_ab=None, rollback_index=chain_header.rollback_index,
        flags=chain_header.flags, rollback_index_location=chain_header.rollback_index_location,
        props=None, props_from_file=None, kernel_cmdlines=None, setup_rootfs_from_kernel=None,
        ht_desc_to_setup=None, include_descriptors_from_image=None, signing_helper=None,
        signing_helper_with_files=None, release_string=chain_header.release_string,
        append_to_release_string=None, required_libavb_version_minor=chain_header.required_libavb_version_minor)
    assert len(blob) <= chain.stat().st_size
    vbmeta = work / 'vbmeta_system.img'
    vbmeta.write_bytes(blob + b'\0' * (chain.stat().st_size - len(blob)))
    _, updated_header, updated_chain, _ = parse_image(avb, avbtool, vbmeta)
    assert avbtool.verify_vbmeta_signature(updated_header, blob)
    def public_key(path, header):
        with path.open('rb') as stream:
            stream.seek(256 + header.authentication_data_block_size + header.public_key_offset)
            return stream.read(header.public_key_size)
    assert public_key(chain, chain_header) == public_key(vbmeta, updated_header)
    assert len(old_chain) == len(updated_chain)
    assert sum(a.encode() != b.encode() for a, b in zip(old_chain, updated_chain)) == 1
    for old, new in zip(old_chain, updated_chain):
        if old.encode() != new.encode():
            assert old is chain_selected[0] and new.encode() == replacement[0].encode()
    for old_header, next_header in ((image_header, new_header), (chain_header, updated_header)):
        for field in ('flags', 'rollback_index', 'rollback_index_location', 'algorithm_type',
                      'required_libavb_version_major', 'required_libavb_version_minor', 'release_string'):
            assert getattr(old_header, field) == getattr(next_header, field)
    assert sha(baseline) == RAW_SHA and sha(chain) == CHAIN_SHA
    destination.mkdir()
    outputs = []
    for partition, source in (('system_ext', image), ('vbmeta_system', vbmeta)):
        target = destination / (partition + '.img')
        shutil.copyfile(source, target)
        assert sha(target) == sha(source)
        outputs.append(dict(partition=partition, name=target.name, bytes=target.stat().st_size, sha256=sha(target)))
    report = dict(revision=args.revision, files=outputs, work_dir=str(work),
                  raw_base_sha256=RAW_SHA, raw_base_bytes=RAW_BYTES, vbmeta_system_base_sha256=CHAIN_SHA,
                  changed_system_ext_files=sorted(SOURCES), compiled_inputs={r: sha(p) for r, p in SOURCES.items()},
                  changed_existing_directory_inodes=directories, new_directories=sorted(created),
                  exact_installed_base_verified=True, filesystem_readback_verified=True,
                  readonly_e2fsck_passed=True, existing_file_inode_metadata_preserved=True,
                  existing_directory_permissions_owners_times_and_xattrs_preserved=True,
                  unrelated_files_preserved=True, partition_sizes_unchanged=True,
                  system_ext_hashtree_verified=True, signatures_verified=True,
                  only_system_ext_avb_descriptor_changed=True, r7_model_descriptor_preserved=True,
                  original_metok_apk_and_certificate_preserved=True, overlay_certificate_matches_framework=True,
                  existing_avb_public_key_preserved=True,
                  new_file_and_directory_metadata_verified=True,
                  hardware_boot_tested=False)
    (destination / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    (destination / 'SHA256SUMS').write_text(''.join(p['sha256'] + '  ' + p['name'] + '\n' for p in outputs))
    (DEVICE / f'docs/system-hardware-followup-r{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
