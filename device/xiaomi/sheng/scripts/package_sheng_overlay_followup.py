#!/usr/bin/env python3
"""Package two device-built ODM overlays over the verified r9 installation.

Only development image copies are changed. Normal builds install these same
device_specific overlays through device.mk; public source remains read-only.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import uuid

from audit_erofs_metadata import metadata
from package_sheng_model_followup import sha, run, parse_image, ROM, HOST, PRODUCT

DEVICE = Path(__file__).resolve().parents[1]
ODM_SHA = '9735c4f6aa8dcc1f3b327b54ebc47f16b4c697e26095f7530d4671dfda3aac4d'
ODM_BYTES = 1141067776
VBMETA_SHA = '488757df791a7cdf9387e2b81b30fbddb2210a6a0ccdf338048dc8f0c75e33af'
VBMETA_BYTES = 8192
INHERITED = {
    'system_ext': ('r9', '7a4e2a739f9cbc3a9713113e40f8a181dde34875c1ef0abee5e53411de58c573'),
    'vbmeta_system': ('r9', 'c0a925d91b33750a09eea0b99beeb759a37c47ac8736112c802a8adbf68eb0f8'),
    'system': ('r7', '50cb7ebad3703ca03734f566aa6ea1f462675f4b361c968849b913b33e932089'),
    'vendor': ('r6', 'c663a57f003d3cd0791ec2a7b50ad36ed1e1d1d96c0b4b414adc5b3bc63ef038'),
}
OVERLAYS = ('FrameworkResOverlaySheng', 'SystemUIResOverlaySheng')


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--revision', type=int, default=10)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    assert args.revision == 10, 'This helper is pinned to the r9 -> r10 baseline'
    base = workspace / 'artifacts/system-hardware-followup-sheng-r5/odm.img'
    chain = workspace / 'artifacts/system-hardware-followup-sheng-r6/vbmeta.img'
    assert base.stat().st_size == ODM_BYTES and sha(base) == ODM_SHA
    assert chain.stat().st_size == VBMETA_BYTES and sha(chain) == VBMETA_SHA
    for partition, (release, digest) in INHERITED.items():
        path = workspace / f'artifacts/system-hardware-followup-sheng-{release}/{partition}.img'
        assert sha(path) == digest, f'Inherited {partition} image mismatch'
    destination = workspace / f'artifacts/system-hardware-followup-sheng-r{args.revision}'
    assert not destination.exists(), 'Never overwrite a built/flashed revision'
    changes = {f'overlay/{name}.apk': PRODUCT / f'odm/overlay/{name}.apk' for name in OVERLAYS}
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
    descriptors = [updated[0] if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == 'odm'
                   else d for d in old_chain]
    blob = avb._generate_vbmeta_blob(algorithm_name='SHA256_RSA4096',
        key_path=str(ROM / 'external/avb/test/data/testkey_rsa4096.pem'),
        public_key_metadata_path=None, descriptors=descriptors, chain_partitions_use_ab=None,
        chain_partitions_do_not_use_ab=None, rollback_index=header.rollback_index, flags=header.flags,
        rollback_index_location=header.rollback_index_location, props=None, props_from_file=None,
        kernel_cmdlines=None, setup_rootfs_from_kernel=None, ht_desc_to_setup=None,
        include_descriptors_from_image=None, signing_helper=None, signing_helper_with_files=None,
        release_string=header.release_string, append_to_release_string=None,
        required_libavb_version_minor=header.required_libavb_version_minor)
    assert len(blob) <= VBMETA_BYTES
    vbmeta = work / 'vbmeta.img'
    vbmeta.write_bytes(blob + b'\0' * (VBMETA_BYTES - len(blob)))
    new_footer, new_header, new_chain, _ = parse_image(avb, avbtool, vbmeta)
    assert avbtool.verify_vbmeta_signature(new_header, blob)
    assert public_key(chain, chain_footer, header) == public_key(vbmeta, new_footer, new_header)
    for field in ('flags', 'rollback_index', 'rollback_index_location', 'algorithm_type',
                  'required_libavb_version_major', 'required_libavb_version_minor', 'release_string'):
        assert getattr(new_header, field) == getattr(header, field), field
    assert len(old_chain) == len(new_chain)
    changed_descriptors = [(a, b) for a, b in zip(old_chain, new_chain) if a.encode() != b.encode()]
    assert len(changed_descriptors) == 1
    assert isinstance(changed_descriptors[0][0], avbtool.AvbHashtreeDescriptor)
    assert changed_descriptors[0][0].partition_name == 'odm'
    destination.mkdir()
    files = []
    for partition, path in (('odm', image), ('vbmeta', vbmeta)):
        target = destination / (partition + '.img')
        shutil.copyfile(path, target)
        assert sha(target) == sha(path)
        files.append(dict(partition=partition, name=target.name, bytes=path.stat().st_size, sha256=sha(path)))
    report = dict(revision=args.revision, files=files, work_dir=str(work),
        raw_base_sha256=ODM_SHA, raw_base_bytes=ODM_BYTES, vbmeta_base_sha256=VBMETA_SHA,
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
    rendered = json.dumps(report, indent=2) + '\n'
    (destination / 'build-result.json').write_text(rendered)
    (destination / 'SHA256SUMS').write_text(''.join(f['sha256'] + '  ' + f['name'] + '\n' for f in files))
    (DEVICE / f'docs/system-hardware-followup-r{args.revision}.json').write_text(rendered)
    print(rendered)


if __name__ == '__main__':
    main()
