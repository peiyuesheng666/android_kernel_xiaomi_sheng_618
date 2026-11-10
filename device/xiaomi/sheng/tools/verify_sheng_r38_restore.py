#!/usr/bin/env python3
"""Verify the complete retained r38 image set before restoring a stock tablet.

Read-only images; emits a manifest for the separately invoked flash helper.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

BASE = {
    'boot': 'de7deddb268bc0f864ca106aa428ad64f07e4c121ff8fa9f19c797a7e0c0ec3c',
    'dtbo': 'ce2f8e51daa162e964da81e43f1ef7e524b3119506c0216d1b7d8a174204d8b0',
    'init_boot': '2c48a30e99b71b1bbd3dc6366c7afa190a242230418928f68aa5563bce620a8f',
    'product': '943933c299688f3b769567ef0d554512614e3cb70c9ce7242083e34d935b9cee',
    'recovery': '738556589abb2c35047879f14cfed63a05a6ed25c7c418a0209709622312376f',
    'system_dlkm': '73e36df936817c4c266ce0ec5a8ff372db9fb5007e6476d6ebd8973f989b2855',
    'system_ext': 'ccda96e9d2590f4aebf8327e9d2fa1f21ec4358cdd4d78add1557d3d0443263c',
    'vendor_boot': '6cfc89bac563d15af78065b592ac8a22d5794826a8cae9be41e033977700fd4a',
    'vendor_dlkm': '94ab3296f0a23c2337fd40e641839e69384cd14e7f83ae76cdfa4ae132d30859',
}
REVISIONS = {'system': 32, 'vbmeta_system': 32, 'odm': 36, 'vendor': 38, 'vbmeta': 38}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def repair_boot_descriptors(avb, avbtool, args, files):
    """Align two retained debug images without changing any other AVB field."""
    paths = {x['partition']: args.workspace / x['path'] for x in files}
    original = paths['vbmeta']
    if sha(original) != '25aec842be41f8afefe440425ce7464c12b0544ecc9591ca4a1950b827472b20':
        raise ValueError('Wrong r38 AVB root')
    image = avbtool.ImageHandler(str(original), read_only=True)
    try:
        footer, header, old, _ = avb._parse_image(image)
    finally:
        image._image.close()
    if footer or header.algorithm_type != 2 or header.flags != 3 or header.public_key_metadata_size:
        raise ValueError('Unexpected r38 AVB header')
    new = copy.deepcopy(old)
    changed = []
    for descriptor in new:
        if not isinstance(descriptor, avbtool.AvbHashDescriptor):
            continue
        path = paths[descriptor.partition_name]
        with path.open('rb') as stream:
            digest = hashlib.new(descriptor.hash_algorithm, descriptor.salt + stream.read(descriptor.image_size)).digest()
        if digest == descriptor.digest:
            continue
        if descriptor.partition_name not in ('init_boot', 'recovery'):
            raise ValueError(f'Unexpected boot descriptor mismatch: {descriptor.partition_name}')
        # These retained raw images include fixed partition padding. Cover the
        # entire supplied partition image rather than guess a stale payload size.
        descriptor.image_size = path.stat().st_size
        descriptor.digest = hashlib.new(descriptor.hash_algorithm, descriptor.salt + path.read_bytes()).digest()
        changed.append(descriptor.partition_name)
    if sorted(changed) != ['init_boot', 'recovery']:
        raise ValueError('Unexpected debug-image delta')
    blob = avb._generate_vbmeta_blob(
        algorithm_name='SHA256_RSA4096',
        key_path=str(args.rom / 'external/avb/test/data/testkey_rsa4096.pem'),
        public_key_metadata_path=None, descriptors=new, chain_partitions_use_ab=None,
        chain_partitions_do_not_use_ab=None, rollback_index=header.rollback_index,
        flags=header.flags, rollback_index_location=header.rollback_index_location,
        props=None, props_from_file=None, kernel_cmdlines=None,
        setup_rootfs_from_kernel=None, ht_desc_to_setup=None,
        include_descriptors_from_image=None, signing_helper=None,
        signing_helper_with_files=None, release_string=header.release_string,
        append_to_release_string=None,
        required_libavb_version_minor=header.required_libavb_version_minor)
    if len(blob) > original.stat().st_size:
        raise ValueError('Repaired AVB root grew')
    data = blob + bytes(original.stat().st_size - len(blob))
    target = args.workspace / 'artifacts/system-hardware-followup-sheng-r38-restore/vbmeta.img'
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError('Refusing to overwrite a different restore root')
    else:
        with target.open('xb') as stream:
            stream.write(data)
    image = avbtool.ImageHandler(str(target), read_only=True)
    try:
        _, updated, verified, _ = avb._parse_image(image)
    finally:
        image._image.close()
    if not avbtool.verify_vbmeta_signature(updated, blob):
        raise ValueError('Repaired root signature failed')
    for field in ('flags', 'rollback_index', 'rollback_index_location', 'algorithm_type',
                  'required_libavb_version_major', 'required_libavb_version_minor', 'release_string'):
        if getattr(header, field) != getattr(updated, field):
            raise ValueError(f'AVB header changed: {field}')
    def public_key(path, h):
        start = h.SIZE + h.authentication_data_block_size + h.public_key_offset
        with path.open('rb') as stream:
            stream.seek(start)
            return stream.read(h.public_key_size)
    if public_key(original, header) != public_key(target, updated):
        raise ValueError('Root public key changed')
    if len(old) != len(verified):
        raise ValueError('Descriptor count changed')
    delta = [getattr(a, 'partition_name', None) for a, b in zip(old, verified) if a.encode() != b.encode()]
    if sorted(delta) != ['init_boot', 'recovery']:
        raise ValueError('Unrelated root descriptor changed')
    for entry in files:
        if entry['partition'] == 'vbmeta':
            entry.update(path=target.relative_to(args.workspace).as_posix(), sha256=sha(target))
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--rom', type=Path, default=Path('/root/sheng-lineage/lineage-24.0'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.rom / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    files = []
    for p in sorted(BASE.keys() | REVISIONS.keys()):
        revision = REVISIONS.get(p, 30)
        relative = f'artifacts/system-hardware-followup-sheng-r{revision}/{p}.img'
        path = args.workspace / relative
        if p in BASE:
            expected = BASE[p]
        else:
            m = json.loads((path.parent / 'build-result.json').read_text())
            if m['revision'] != revision:
                raise ValueError(f'Wrong package revision: {p}')
            entry, = [x for x in m['files'] if x['partition'] == p]
            expected = entry['sha256']
            if path.stat().st_size != entry['bytes']:
                raise ValueError(f'Wrong image size: {p}')
        if sha(path) != expected:
            raise ValueError(f'Image hash mismatch: {p}')
        files.append(dict(partition=p, path=relative, bytes=path.stat().st_size, sha256=expected))
        print(f'{p}: SHA256 verified', flush=True)
    repaired = repair_boot_descriptors(avb, avbtool, args, files)
    # AVB follows filenames adjacent to the root image. Symlinks create a
    # temporary view of the cumulative batch without copying or editing it.
    with tempfile.TemporaryDirectory(prefix='sheng-r38-chain-') as tmp:
        root = Path(tmp)
        for entry in files:
            (root / (entry['partition'] + '.img')).symlink_to((args.workspace / entry['path']).resolve())
        log = subprocess.run([str(args.rom / 'out/host/linux-x86/bin/avbtool'),
                              'verify_image', '--image', str(root / 'vbmeta.img'),
                              '--follow_chain_partitions'], capture_output=True, text=True)
        args.output.with_suffix('.avb.txt').write_text(log.stdout + log.stderr)
        if log.returncode:
            print(log.stdout + log.stderr)
            raise RuntimeError('Full AVB chain verification failed')
    manifest = dict(revision=38, date_utc=datetime.now(timezone.utc).isoformat(),
                    target='ca10ede3/sheng', restore_slot='a',
                    complete_avb_chain_verified=True, files=files,
                    boot_descriptors_aligned=repaired, original_root_flags_preserved=True,
                    userdata_erase_authorized=False, source_sha256=sha(Path(__file__)),
                    full_product_build_passed=False)
    args.output.write_text(json.dumps(manifest, indent=2) + '\n')
    print('Complete r38 image hashes and AVB chain verified.', flush=True)


if __name__ == '__main__':
    main()
