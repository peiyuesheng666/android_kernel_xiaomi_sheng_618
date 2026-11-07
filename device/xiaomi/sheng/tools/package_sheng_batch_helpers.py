#!/usr/bin/env python3
"""Filesystem stages shared by the explicitly scoped development batch packer."""
import ctypes
import errno
import hashlib
import json
import ntpath
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess

from package_sheng_location_followup import certify_existing_inodes, debugfs
from package_sheng_model_followup import HOST, PRODUCT, ROM, changed_blocks, parse_image, run, sha
from package_sheng_overlay_followup import (
    certificates, complete_metadata, contents, ext4_snapshot, public_key,
    replace_chain_hashtree,
)

if not __debug__:
    raise RuntimeError('Packaging verification requires Python assertions; do not use -O')

SEPOLICY_CONTEXTS = 'out/soong/.intermediates/system/sepolicy/file_contexts.concat.tmp/android_common/gen/file_contexts.concat.tmp'


def packaging_input_path(relative):
    if relative == '@sepolicy_file_contexts':
        return ROM / SEPOLICY_CONTEXTS
    assert not relative.startswith('@'), 'Unknown reserved packaging input'
    return PRODUCT / relative_path(relative)


def erofs_input_keys(partition):
    return {'@sepolicy_file_contexts',
            f'obj/PACKAGING/{partition}_intermediates/{partition}_image_info.txt'}


def validate_packaging_inputs(partitions, build_inputs):
    required = set().union(*(erofs_input_keys(p) for p in partitions if p in ('odm', 'vendor')))
    assert required <= set(build_inputs), f'Missing frozen EROFS inputs: {sorted(required - set(build_inputs))}'
    for relative, digest in build_inputs.items():
        target = packaging_input_path(relative)
        root = ROM if relative == '@sepolicy_file_contexts' else PRODUCT
        assert target.is_file() and not target.is_symlink()
        assert target.resolve().is_relative_to(root.resolve()) and sha(target) == digest, relative


def erofs_command(partition, props, root, image, config, contexts, old_uuid):
    """Use compiled mkfs directly: the global build_image CLI discards fs_config and UUID."""
    assert props.get(partition + '_fs_type', props.get('fs_type')) == 'erofs'
    assert not props.get('erofs_default_compress_hints') and not props.get(partition + '_erofs_compress_hints'), \
        'Compression hints need an explicitly frozen input before they can be supported'
    command = [HOST / 'mkfs.erofs', '--mount-point', partition, '--fs-config-file', config,
               '--file-contexts', contexts, '-U', old_uuid]
    compressor = props.get(partition + '_erofs_compressor', props.get('erofs_default_compressor'))
    if compressor and compressor != 'none':
        command += ['-z', compressor]
    command += ['-b', props.get(partition + '_erofs_blocksize', props.get('erofs_blocksize', '4096'))]
    cluster = props.get(partition + '_erofs_pcluster_size', props.get('erofs_pcluster_size'))
    if cluster:
        command += ['-C', cluster]
    options = []
    if 'erofs_use_legacy_compression' in props:
        options.append('legacy-compress')
    if props.get(partition + '_erofs_share_dup_blocks', props.get('erofs_share_dup_blocks')) is not None:
        command += ['--chunksize', '4096']
    if props.get(partition + '_erofs_enable_dedupe', props.get('erofs_enable_dedupe')) is not None:
        options.append('dedupe')
    if options:
        command += ['-E', ','.join(options)]
    return command + [image, root]


def relative_path(value):
    path = PurePosixPath(value)
    assert value and not path.is_absolute() and str(path) == value
    assert '..' not in path.parts and re.fullmatch(r'[A-Za-z0-9_./@+:-]+', value), value
    return value


def safe_target(root, relative):
    relative_path(relative)
    target = root / relative
    for parent in [target] + list(target.parents):
        assert not parent.is_symlink(), f'Symlink in update path: {parent}'
        if parent == root:
            break
    assert target.resolve().is_relative_to(root.resolve()), target
    return target


def sibling_symlink_target(relative, link):
    relative_path(link)
    assert len(PurePosixPath(link).parts) == 1 and link not in ('.', '..'), \
        'A new alias may point only to a relative sibling filename'
    return str(PurePosixPath(relative).parent / link)


def installed_symlink_target(partition, relative, link):
    # The stock sheng AON alias is the only supported cross-partition link.
    if (partition, relative, link) == (
            'vendor', 'lib64/camera/aon_front.pb', '/odm/lib64/camera/aon_front.pb'):
        return 'odm', 'lib64/camera/aon_front.pb'
    return partition, sibling_symlink_target(relative, link)


def validate_inputs(partition, entries, allow_symlinks=False, installed_sources=None):
    # A renamed replacement module may have a new installed build directory
    # while a scoped development update retains the existing on-device path.
    # Both sides must be explicit relative paths within the same partition.
    installed_sources = installed_sources or {}
    assert set(installed_sources) <= set(entries), 'Unused installed-source mapping'
    assert len(set(installed_sources.values())) == len(installed_sources), 'Duplicate mapped source'
    result = {}
    for relative, entry in entries.items():
        relative_path(relative)
        installed = relative_path(installed_sources.get(relative, relative))
        source = PRODUCT / partition / installed
        assert entry['source'] == str(source), 'Sources must be exact installed build outputs'
        assert source.parent.resolve().is_relative_to((PRODUCT / partition).resolve()), source
        if entry.get('kind', 'file') == 'symlink':
            assert relative not in installed_sources, 'Symlink inputs cannot be remapped'
            assert allow_symlinks and partition in ('odm', 'vendor') and source.is_symlink(), source
            raw = os.readlink(source)
            target_partition, target_relative = installed_symlink_target(partition, relative, raw)
            assert raw == entry['link_target']
            data = raw.encode('utf-8')
            assert len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256'], source
            target = PRODUCT / target_partition / target_relative
            assert target.is_file() and not target.is_symlink()
            assert target.resolve().is_relative_to((PRODUCT / target_partition).resolve())
            assert sha(target) == entry['target_sha256'], target
            assert not entry.get('device_source'), 'Generated aliases are frozen through their build entry and DT inputs'
        else:
            assert source.resolve().is_relative_to((PRODUCT / partition).resolve()), source
            assert entry.get('kind', 'file') == 'file' and source.is_file() and not source.is_symlink(), source
            assert source.stat().st_size == entry['bytes'] and sha(source) == entry['sha256'], source
        if entry.get('device_source'):
            device = Path(__file__).resolve().parents[1]
            tree = device / relative_path(entry['device_source'])
            assert tree.resolve().is_relative_to(device.resolve()) and not tree.is_symlink()
            assert tree.read_bytes() == source.read_bytes(), tree
        result[relative] = source
    assert result, f'Empty {partition} stage'
    return result


def tree_descriptor(avb, avbtool, image, partition):
    footer, header, descriptors, _ = parse_image(avb, avbtool, image)
    selected = [d for d in descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)
                and d.partition_name == partition]
    assert footer and len(selected) == 1
    assert header.algorithm_type == header.public_key_metadata_size == 0
    assert selected[0].flags == 0 and selected[0].hash_algorithm == 'sha256'
    return footer, header, descriptors, selected[0]


def verify_seal(avb, avbtool, base, image, partition, fixed_payload=False):
    old_footer, old_header, old_descriptors, old_tree = tree_descriptor(avb, avbtool, base, partition)
    new_footer, new_header, new_descriptors, new_tree = tree_descriptor(avb, avbtool, image, partition)
    run([HOST / 'avbtool', 'verify_image', '--image', image], capture_output=True)
    assert image.stat().st_size == base.stat().st_size
    for field in ('flags', 'rollback_index', 'rollback_index_location', 'algorithm_type',
                  'required_libavb_version_major', 'required_libavb_version_minor', 'release_string'):
        assert getattr(old_header, field) == getattr(new_header, field), field
    fields = ('dm_verity_version', 'data_block_size', 'hash_block_size',
              'fec_num_roots', 'hash_algorithm', 'salt', 'flags')
    if fixed_payload:
        fields += ('image_size', 'tree_offset', 'tree_size', 'fec_offset', 'fec_size')
    for field in fields:
        assert getattr(old_tree, field) == getattr(new_tree, field), field
    assert old_tree.root_digest != new_tree.root_digest
    assert [d.encode() for d in old_descriptors if d is not old_tree] == [
        d.encode() for d in new_descriptors if d is not new_tree]
    assert old_footer.original_image_size == old_tree.image_size
    assert new_footer.original_image_size == new_tree.image_size
    return new_tree


def new_metadata(value, directory=False, nlink=1, symlink=False):
    assert set(value) == {'uid', 'gid', 'mode', 'mtime_ns', 'selinux'}, value
    assert value['uid'] >= 0 and value['gid'] >= 0 and 0 <= value['mode'] <= 0o7777
    assert value['mtime_ns'] >= 0 and value['mtime_ns'] % 1_000_000_000 == 0
    assert re.fullmatch(r'u:object_r:[A-Za-z0-9_.-]+:s0', value['selinux'])
    return dict(uid=value['uid'], gid=value['gid'], mode=value['mode'],
                mtime_ns=value['mtime_ns'], type=stat.S_IFDIR if directory else stat.S_IFLNK if symlink else stat.S_IFREG,
                nlink=nlink, xattrs={'6:selinux': (value['selinux'] + '\0').encode().hex()})


def stage_erofs(partition, base, entries, nodes, work, avb, avbtool, new_apk_certificates=None,
                external_symlink_targets=None):
    """Update only declared paths; preserve original EROFS metadata and UUID."""
    sources = validate_inputs(partition, entries, allow_symlinks=True)
    new_apk_certificates = new_apk_certificates or {}
    external_symlink_targets = external_symlink_targets or {}
    used_external_targets = set()
    new_apks = set()
    root = work / f'{partition}-tree'
    assert not root.exists() and not (work / f'{partition}.img').exists()
    run([HOST / 'fsck.erofs', '-d0', '--extract=' + str(root), '--preserve', base],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    before = contents(root)
    metadata_before, old_uuid = complete_metadata(base)
    expected = {p: dict(v) for p, v in metadata_before.items()}
    new_nodes, signer_digests, aliases = set(), {}, {}
    for relative, source in sources.items():
        target = safe_target(root, relative)
        parent = target.parent
        while parent != root and not parent.exists():
            new_nodes.add(str(parent.relative_to(root)))
            parent = parent.parent
        target.parent.mkdir(parents=True, exist_ok=True)
        if entries[relative].get('kind') == 'symlink':
            assert not os.path.lexists(target), 'Existing aliases must never be replaced'
            raw = entries[relative]['link_target']
            target_partition, target_relative = installed_symlink_target(partition, relative, raw)
            if target_partition == partition:
                assert before.get(target_relative) == ('file', entries[relative]['target_sha256']), \
                    'Alias target must be an unchanged baseline blob matching the compiled target'
                assert target_relative not in sources, 'Alias target may not be updated in the same stage'
            else:
                assert external_symlink_targets.get(raw) == entries[relative]['target_sha256'], \
                    'Cross-partition alias requires a separately verified baseline target'
                used_external_targets.add(raw)
            target.symlink_to(raw)
            new_nodes.add(relative)
            aliases[relative] = dict(link_target=raw, target_sha256=entries[relative]['target_sha256'])
            continue
        if target.exists():
            assert target.is_file() and not target.is_symlink(), relative
            assert metadata_before['/' + relative]['nlink'] == 1, 'Hardlink replacement is forbidden'
        else:
            new_nodes.add(relative)
        if relative.endswith('.apk'):
            certs = certificates(source)
            if target.is_file():
                assert certificates(target) == certs
            else:
                signing_reference = new_apk_certificates.get(relative)
                assert signing_reference and all(
                    re.fullmatch(r'[0-9a-f]{64}', digest) for digest in signing_reference
                ), 'New EROFS APK requires a separately pinned signing reference'
                assert certs == signing_reference, relative
                new_apks.add(relative)
            signer_digests[relative] = certs
        shutil.copyfile(source, target)
    assert new_apks == set(new_apk_certificates), 'Unused or missing new APK signing reference'
    assert used_external_targets == set(external_symlink_targets), 'Unused cross-partition target'
    assert new_nodes == set(nodes), f'New node metadata must be explicit: {sorted(new_nodes)}'
    for relative in sorted(new_nodes):
        target = root / relative
        directory = target.is_dir()
        links = 2 + sum(p.is_dir() for p in target.iterdir()) if directory else 1
        expected['/' + relative] = new_metadata(nodes[relative], directory, links, target.is_symlink())
        # mkfs.erofs writes the SELinux value without ext4's terminating NUL.
        expected['/' + relative]['xattrs']['6:selinux'] = nodes[relative]['selinux'].encode().hex()
        if directory:
            key = '' if target.parent == root else '/' + str(target.parent.relative_to(root))
            if key in metadata_before:
                expected[key] = dict(expected[key], nlink=expected[key]['nlink'] + 1)
    for relative, inode in expected.items():
        target = root / relative.lstrip('/')
        os.utime(target, ns=(inode['mtime_ns'], inode['mtime_ns']), follow_symlinks=False)
    after = contents(root)
    changed = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
    wanted = {p for p in sources if before.get(p) != (
        ('link', entries[p]['link_target']) if entries[p].get('kind') == 'symlink' else ('file', entries[p]['sha256']))}
    assert changed == wanted and changed, f'Unexpected {partition} content delta: {sorted(changed)}'
    config = work / f'{partition}-filesystem-config.txt'
    lines = []
    for relative, inode in sorted(expected.items()):
        raw, capability = inode['xattrs'].get('6:capability'), 0
        if raw:
            fields = struct.unpack('<5I', bytes.fromhex(raw))
            assert fields[0] == 0x02000001 and fields[2] == fields[4] == 0
            capability = fields[1] | fields[3] << 32
        name = partition + relative if relative else ''
        lines.append(f"{name} {inode['uid']} {inode['gid']} {inode['mode']:o} capabilities=0x{capability:x}")
    config.write_text('\n'.join(lines) + '\n')
    contexts = packaging_input_path('@sepolicy_file_contexts')
    contexts_bin = work / f'{partition}-file-contexts.bin'
    run([HOST / 'sefcontext_compile', '-o', contexts_bin, contexts])
    props_path = PRODUCT / f'obj/PACKAGING/{partition}_intermediates/{partition}_image_info.txt'
    props = dict(line.split('=', 1) for line in props_path.read_text().splitlines() if '=' in line)
    _, image_header, descriptors, tree = tree_descriptor(avb, avbtool, base, partition)
    args = ['--hash_algorithm', tree.hash_algorithm, '--salt', tree.salt.hex(),
            '--block_size', str(tree.data_block_size), '--fec_num_roots', str(tree.fec_num_roots),
            '--rollback_index', str(image_header.rollback_index),
            '--rollback_index_location', str(image_header.rollback_index_location),
            '--flags', str(image_header.flags)]
    for descriptor in descriptors:
        if isinstance(descriptor, avbtool.AvbPropertyDescriptor):
            args += ['--prop', descriptor.key + ':' + descriptor.value.decode()]
        else:
            assert descriptor is tree
    image = work / f'{partition}.img'
    with (work / f'{partition}-build.log').open('w') as log:
        run(erofs_command(partition, props, root, image, config, contexts_bin, old_uuid),
            stdout=log, stderr=subprocess.STDOUT)
    run([HOST / 'avbtool', 'add_hashtree_footer', '--image', image,
         '--partition_name', partition, '--partition_size', base.stat().st_size,
         '--algorithm', 'NONE', '--internal_release_string', image_header.release_string] + args,
        capture_output=True)
    descriptor = verify_seal(avb, avbtool, base, image, partition)
    readback = work / f'{partition}-readback'
    run([HOST / 'fsck.erofs', '-d0', '--extract=' + str(readback), '--preserve', image],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert contents(readback) == after
    actual, new_uuid = complete_metadata(image)
    assert actual == expected, f'{partition} inode metadata differs from the explicit delta'
    assert old_uuid == new_uuid
    validate_inputs(partition, entries, allow_symlinks=True)
    return image, descriptor, dict(changed_files=sorted(changed), metadata_preserved=True,
                                  erofs_uuid=old_uuid, apk_certificates=signer_digests, created_symlinks=aliases,
                                  baseline_entries={p: before.get(p) for p in sources})


def inode_number(image, name):
    value = debugfs(image, f'stat {name}')
    match = re.search(r'Inode:\s*(\d+)', value)
    assert match, f'Cannot read inode {name}: {value}'
    return int(match[1])


def inode_offset(snapshot, number):
    group, index = divmod(number - 1, snapshot['inodes_per_group'])
    return snapshot['groups'][group][2] * snapshot['block_size'] + index * 256


def stage_ext4(partition, base, entries, nodes, work, avb, avbtool, platform_certificate,
               installed_sources=None):
    """Add declared nodes or replace single-link files, retaining unrelated inode bytes."""
    sources = validate_inputs(partition, entries, installed_sources=installed_sources)
    prefix = 'system/' if partition == 'system' else ''
    paths = {p: prefix + p for p in sources}
    before_root = work / f'{partition}-before'
    assert not (work / f'{partition}.img').exists()
    before_root.mkdir()
    debugfs(base, f'rdump / {before_root}')
    before_files = contents(before_root)
    old = ext4_snapshot(base)
    _, old_header, descriptors, tree = tree_descriptor(avb, avbtool, base, partition)
    assert tree.data_block_size == tree.hash_block_size == 4096 and tree.fec_num_roots == 2
    image = work / f'{partition}.img'
    shutil.copyfile(base, image)
    run([HOST / 'avbtool', 'erase_footer', '--image', image], capture_output=True)
    assert image.stat().st_size == tree.image_size
    replaced, created, changed_paths = {}, set(), set()
    affected_dirs = {inode_number(base, '/')}
    for relative, source in sources.items():
        fs_relative = paths[relative]
        target = safe_target(before_root, fs_relative)
        if before_files.get(fs_relative) == ('file', sha(source)):
            continue
        changed_paths.add(fs_relative)
        if target.exists():
            assert target.is_file() and not target.is_symlink()
            number = inode_number(base, '/' + fs_relative)
            inode = old['inodes'][number]
            assert struct.unpack_from('<H', inode, 26)[0] == 1 and struct.unpack_from('<I', inode, 104)[0] == 0
            replaced[fs_relative] = (number, inode)
            if relative.endswith('.apk'):
                assert certificates(source) == certificates(target)
            debugfs(image, f'rm /{fs_relative}', write=True)
        elif relative.endswith('.apk'):
            assert certificates(source) == platform_certificate
        parent = PurePosixPath(fs_relative).parent
        for current in reversed([parent] + list(parent.parents)):
            if str(current) == '.':
                continue
            if (before_root / str(current)).is_dir():
                affected_dirs.add(inode_number(base, '/' + str(current)))
            elif str(current) not in created:
                assert str(current).removeprefix(prefix) in nodes
                debugfs(image, f'mkdir /{current}', write=True)
                created.add(str(current))
        debugfs(image, f'write {source} /{fs_relative}', write=True)
        if fs_relative not in replaced:
            created.add(fs_relative)
    assert created == {prefix + p for p in nodes}, 'Every new ext4 node requires explicit metadata'
    for fs_relative in sorted(created):
        name = '/' + fs_relative
        directory = (before_root / fs_relative).is_dir() or fs_relative not in changed_paths
        value = nodes[fs_relative.removeprefix(prefix)]
        meta = new_metadata(value, directory)
        debugfs(image, f'set_inode_field {name} mode 0{((stat.S_IFDIR if directory else stat.S_IFREG) | meta["mode"]):o}', write=True)
        for field, number in (('uid', meta['uid']), ('gid', meta['gid'])):
            debugfs(image, f'set_inode_field {name} {field} {number}', write=True)
        for field in ('atime', 'mtime', 'ctime', 'crtime'):
            debugfs(image, f'set_inode_field {name} {field} @{meta["mtime_ns"] // 1_000_000_000}', write=True)
        context = work / f'{partition}-label-{len(list(created))}-{inode_number(image, name)}'
        context.write_bytes(bytes.fromhex(meta['xattrs']['6:selinux']))
        debugfs(image, f'ea_set -f {context} {name} security.selinux', write=True)
    current = ext4_snapshot(image)
    with image.open('r+b') as stream:
        for name, (_, inode) in replaced.items():
            offset = inode_offset(current, inode_number(image, '/' + name))
            for start, end in ((0, 4), (8, 28), (32, 40), (100, 108), (112, 256)):
                stream.seek(offset + start)
                stream.write(inode[start:end])
        for number in affected_dirs:
            offset, inode = inode_offset(current, number), old['inodes'][number]
            for start, end in ((0, 4), (8, 26), (32, 40), (100, 108), (112, 256)):
                stream.seek(offset + start)
                stream.write(inode[start:end])
        for offset, original in old['supers'].items():
            masked = bytearray(current['supers'][offset])
            for start, end in ((12, 20), (48, 52), (376, 384)):
                masked[start:end] = original[start:end]
            assert masked == original, 'Unrelated superblock field changed'
            for start, end in ((48, 52), (376, 384)):
                stream.seek(offset + start)
                stream.write(original[start:end])
    final = ext4_snapshot(image)
    replaced_numbers = {number for number, _ in replaced.values()}
    preserved = {n: inode for n, inode in old['inodes'].items() if n not in replaced_numbers}
    assert set(certify_existing_inodes(preserved, final['inodes'])) <= affected_dirs
    assert final['external_xattrs'] == old['external_xattrs']
    new_numbers = {inode_number(image, '/' + name) for name in created | set(replaced)}
    assert final['inodes'].keys() - old['inodes'].keys() == new_numbers - old['inodes'].keys()
    assert old['inodes'].keys() - final['inodes'].keys() <= replaced_numbers
    for name, (_, original) in replaced.items():
        actual = final['inodes'][inode_number(image, '/' + name)]
        for start, end in ((0, 4), (8, 28), (32, 40), (100, 108), (112, 256)):
            assert actual[start:end] == original[start:end], f'Replaced file metadata changed: {name}'
    for fs_relative in created:
        number = inode_number(image, '/' + fs_relative)
        inode, meta = final['inodes'][number], nodes[fs_relative.removeprefix(prefix)]
        directory = fs_relative not in changed_paths
        assert struct.unpack_from('<H', inode, 0)[0] & 0o170000 == (stat.S_IFDIR if directory else stat.S_IFREG)
        assert struct.unpack_from('<I', inode, 104)[0] == 0, 'New label must remain inline'
        assert struct.unpack_from('<H', inode, 0)[0] & 0o7777 == meta['mode']
        assert struct.unpack_from('<H', inode, 2)[0] == meta['uid'] and struct.unpack_from('<H', inode, 24)[0] == meta['gid']
        assert all(struct.unpack_from('<H', inode, p)[0] == 0 for p in (120, 122))
        assert all(struct.unpack_from('<I', inode, p)[0] == meta['mtime_ns'] // 1_000_000_000 for p in (8, 12, 16, 144))
        assert all(struct.unpack_from('<I', inode, p)[0] == 0 for p in (132, 136, 140, 148))
        label = work / f'{partition}-label-readback-{number}'
        debugfs(image, f'ea_get -f {label} /{fs_relative} security.selinux')
        assert label.read_bytes() == (meta['selinux'] + '\0').encode()
    fsck = run(['e2fsck', '-fn', image], capture_output=True, text=True)
    (work / f'{partition}-e2fsck.log').write_text(fsck.stdout + fsck.stderr)
    after_root = work / f'{partition}-after'
    after_root.mkdir()
    debugfs(image, f'rdump / {after_root}')
    after_files = contents(after_root)
    assert {p for p in before_files.keys() | after_files.keys() if before_files.get(p) != after_files.get(p)} == changed_paths
    for relative, source in sources.items():
        assert after_files[paths[relative]] == ('file', sha(source))
    args = [HOST / 'avbtool', 'add_hashtree_footer', '--image', image,
            '--partition_size', base.stat().st_size, '--partition_name', partition,
            '--hash_algorithm', tree.hash_algorithm, '--salt', tree.salt.hex(),
            '--block_size', tree.data_block_size, '--fec_num_roots', tree.fec_num_roots,
            '--algorithm', 'NONE', '--rollback_index', old_header.rollback_index,
            '--rollback_index_location', old_header.rollback_index_location, '--flags', old_header.flags]
    for descriptor in descriptors:
        if isinstance(descriptor, avbtool.AvbPropertyDescriptor):
            args += ['--prop', descriptor.key + ':' + descriptor.value.decode()]
        else:
            assert descriptor is tree
    run(args, capture_output=True)
    descriptor = verify_seal(avb, avbtool, base, image, partition, fixed_payload=True)
    validate_inputs(partition, entries, installed_sources=installed_sources)
    return image, descriptor, dict(changed_files=sorted(changed_paths), metadata_preserved=True,
                                  created_nodes=sorted(created), replaced_files=sorted(replaced),
                                  filesystem_changed_blocks=changed_blocks(base, image, tree.image_size, tree.data_block_size))


def merge_parent(avb, avbtool, base, replacements, output, algorithm, work):
    names = {d.partition_name for d in replacements}
    assert replacements and len(names) == len(replacements)
    assert output.resolve() != base.resolve() and not output.exists()
    old_footer, old_header, old, _ = parse_image(avb, avbtool, base)
    current = base
    for index, replacement in enumerate(replacements):
        target = output if index == len(replacements) - 1 else work / f'{output.stem}-{index}.img'
        replace_chain_hashtree(avb, avbtool, current, replacement, target, algorithm)
        current = target
    new_footer, new_header, new, _ = parse_image(avb, avbtool, output)
    differences = [(a, b) for a, b in zip(old, new) if a.encode() != b.encode()]
    assert len(old) == len(new) and len(differences) == len(names)
    assert all(isinstance(a, avbtool.AvbHashtreeDescriptor) and a.partition_name in names for a, _ in differences)
    assert {b.partition_name: b.encode() for _, b in differences} == {d.partition_name: d.encode() for d in replacements}
    assert public_key(base, old_footer, old_header) == public_key(output, new_footer, new_header)


def linux_rename_noreplace(stage, destination):
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(stage), -100, os.fsencode(destination), 1):
        value = ctypes.get_errno()
        raise OSError(value, os.strerror(value), str(destination))


def windows_path(path):
    result = run(['wslpath', '-w', str(path)], capture_output=True, text=True)
    value = result.stdout.rstrip('\r\n')
    assert value and '\n' not in value and '\r' not in value, path
    return value


def windows_directory_move(stage, destination):
    """Use a fixed Windows script and native non-overwriting directory move on drvfs."""
    assert stage.is_absolute() and destination.is_absolute() and stage.parent == destination.parent
    mount = run(['findmnt', '-n', '-T', str(stage), '-o', 'FSTYPE,OPTIONS'],
                capture_output=True, text=True).stdout.strip()
    assert mount.split(None, 1)[0] == '9p' and 'aname=drvfs' in mount, \
        'Windows atomic fallback is limited to a drvfs mount'
    executable = shutil.which('powershell.exe')
    assert executable, 'Windows PowerShell is required for atomic publication on drvfs'
    script = Path(__file__).resolve().with_name('publish_sheng_batch_windows.ps1')
    assert script.is_file() and not script.is_symlink()
    # wslpath follows a Junction for the existing stage but may retain the lexical
    # drive for an absent destination. Map their existing common parent once.
    parent = windows_path(stage.parent)
    request = dict(source=ntpath.join(parent, stage.name),
                   destination=ntpath.join(parent, destination.name))
    # Paths are data on stdin; no shell, interpolation, Move-Item, or overwrite flags.
    result = run([executable, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                  '-File', windows_path(script)], input=json.dumps(request).encode('utf-8'),
                 capture_output=True)
    assert json.loads(result.stdout.decode('utf-8-sig')) == {'published': True}


def publish_directory(stage, destination):
    assert stage.parent == destination.parent
    try:
        linux_rename_noreplace(stage, destination)
    except OSError as error:
        if error.errno not in (errno.EINVAL, errno.ENOTSUP):
            raise
        windows_directory_move(stage, destination)


def publish_batch(destination, outputs, report):
    """Verify the entire sibling staging directory, then publish without overwrite."""
    assert destination.is_absolute() and not os.path.lexists(destination)
    stage = destination.with_name('.' + destination.name + '-publishing')
    stage.mkdir()  # Retain this diagnostic directory on failure; never delete a computed tree.
    files = []
    for partition, source in sorted(outputs.items()):
        assert partition in {'system', 'system_ext', 'vendor', 'odm', 'vbmeta', 'vbmeta_system'}
        target = stage / (partition + '.img')
        shutil.copyfile(source, target)
        digest = sha(source)
        assert target.stat().st_size == source.stat().st_size and sha(target) == digest
        files.append(dict(partition=partition, name=target.name, bytes=target.stat().st_size, sha256=digest))
    report['files'] = files
    (stage / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    (stage / 'SHA256SUMS').write_text(''.join(f['sha256'] + '  ' + f['name'] + '\n' for f in files))
    for item in files:
        assert sha(stage / item['name']) == item['sha256']
    publish_directory(stage, destination)
    assert destination.is_dir() and not stage.exists()
