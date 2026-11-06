#!/usr/bin/env python3
"""Build the r3 startup delta over the verified r2 vendor/AVB images.

Normal ROM builds install these sources through the device's build rules.
This local development helper preserves every other installed partition.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys

from audit_erofs_metadata import metadata

device = Path(__file__).resolve().parents[1]
workspace = device.parents[2]
rom = Path('/root/sheng-lineage/lineage-24.0')
product = rom/'out/target/product/sheng'
host = rom/'out/host/linux-x86/bin'
base = workspace/'artifacts/system-hardware-followup-sheng-r2'
destination = workspace/'artifacts/system-hardware-followup-sheng-r3'
assert not destination.exists(), 'Never overwrite a built/flashed revision.'
build = Path('/root/sheng-lineage/hardware-followup')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
build.mkdir(parents=True)
environment = dict(os.environ, PATH=str(host)+':'+os.environ['PATH'],
                   LANG='C.UTF-8', LC_ALL='C.UTF-8')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, env=environment, **kwargs)


def contents(root):
    return {str(path.relative_to(root)):
            ('link', os.readlink(path)) if path.is_symlink() else ('file', sha(path))
            for path in root.rglob('*') if path.is_symlink() or path.is_file()}


for name, expected in {
    'vendor.img': 'ad30430f551ddef2f762e0800bcca97f389be6a97f5f69f737c186736d02adf5',
    'vbmeta.img': 'a81f46817a109441ec8e5a6495b2d953ee00dc28799b65c0ecf61e20755f2400',
}.items():
    assert sha(base/name) == expected, name

vendor = build/'vendor'
run([host/'fsck.erofs', '-d0', '--extract='+str(vendor), '--preserve', base/'vendor.img'],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
before = contents(vendor)
original_metadata = metadata(base/'vendor.img')
changes = {relative: product/'vendor'/relative for relative in (
    'bin/hw/vendor.qti.hardware.display.composer-service-sheng',
    'etc/init/android.hardware.sensors-service.sheng-multihal.rc',
    'etc/init/init.sm8550.rc',
)}
for relative, source in changes.items():
    target = vendor/relative
    assert target.is_file() and source.is_file(), relative
    shutil.copyfile(source, target)

# Both RC files must be build outputs of this device tree, with a single
# canonical sensor service and no reference to the removed executable.
for relative, source in (
    ('etc/init/init.sm8550.rc', device/'rootdir/etc/init.sm8550.rc'),
    ('etc/init/android.hardware.sensors-service.sheng-multihal.rc',
     device/'aidl/sensors/android.hardware.sensors-service.sheng-multihal.rc'),
):
    assert sha(changes[relative]) == sha(source), relative
rc_files = list((vendor/'etc/init').rglob('*.rc'))
assert sum(line.startswith('service vendor.sensors-hal-multihal ')
           for path in rc_files for line in path.read_text().splitlines()) == 1
assert all('android.hardware.sensors-service.xiaomi-multihal' not in path.read_text()
           for path in rc_files)

after = contents(vendor)
changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
assert changed == set(changes), changed

# Derive filesystem config from the installed image, including executable
# ownership and capabilities. Exact inode/xattr equality is checked below.
config = build/'vendor_filesystem_config.txt'
entries = []
for relative, inode in sorted(original_metadata.items()):
    capability = 0
    raw = inode['xattrs'].get('6:capability')
    if raw:
        fields = struct.unpack('<5I', bytes.fromhex(raw))
        assert fields[0] == 0x02000001 and fields[2] == fields[4] == 0, fields
        capability = fields[1] | (fields[3] << 32)
    name = 'vendor'+relative if relative else ''
    entries.append(f"{name} {inode['uid']} {inode['gid']} {inode['mode']:o} capabilities=0x{capability:x}")
config.write_text('\n'.join(entries)+'\n')
contexts = rom/'out/soong/.intermediates/system/sepolicy/file_contexts.concat.tmp/android_common/gen/file_contexts.concat.tmp'
run([host/'sefcontext_compile', '-o', build/'file_contexts.bin', contexts])
file_list = build/'vendor_file_list.txt'
file_list.write_text('\n'.join(sorted(str(p.relative_to(vendor)) for p in vendor.rglob('*')))+'\n')
props = dict(line.split('=', 1) for line in
             (product/'obj/PACKAGING/vendor_intermediates/vendor_image_info.txt').read_text().splitlines()
             if '=' in line)
props.update(use_dynamic_partition_size='false', vendor_size=str((base/'vendor.img').stat().st_size),
             fs_config=str(config), vendor_selinux_fc=str(build/'file_contexts.bin'))
info = build/'vendor_image_info.txt'
info.write_text('\n'.join(key+'='+value for key, value in props.items())+'\n')
image = build/'vendor.img'
with (build/'vendor-build.log').open('w') as log:
    run([host/'build_image', '--input-directory-filter-file', file_list, vendor, info, image, product/'system'],
        cwd=rom, stdout=log, stderr=subprocess.STDOUT)
assert image.stat().st_size == (base/'vendor.img').stat().st_size
run([host/'avbtool', 'verify_image', '--image', image], capture_output=True)
readback = build/'vendor-readback'
run([host/'fsck.erofs', '-d0', '--extract='+str(readback), '--preserve', image],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
assert contents(readback) == after
assert metadata(image) == original_metadata, 'Inode ownership/modes/xattrs must be preserved.'

# Replace only vendor's hashtree descriptor. In particular, retain the r2 ODM
# descriptor and every other installed chain, rollback value and AVB flag.
sys.path.insert(0, str(rom/'external/avb'))
import avbtool
avb = avbtool.Avb()
_, header, old, _ = avb._parse_image(avbtool.ImageHandler(str(base/'vbmeta.img'), read_only=True))
_, _, embedded, _ = avb._parse_image(avbtool.ImageHandler(str(image), read_only=True))
updated = [d for d in embedded if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == 'vendor']
assert len(updated) == 1
descriptors = [updated[0] if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == 'vendor' else d for d in old]
blob = avb._generate_vbmeta_blob(algorithm_name='SHA256_RSA4096',
    key_path=str(rom/'external/avb/test/data/testkey_rsa4096.pem'),
    public_key_metadata_path=None, descriptors=descriptors, chain_partitions_use_ab=None,
    chain_partitions_do_not_use_ab=None, rollback_index=header.rollback_index, flags=header.flags,
    rollback_index_location=header.rollback_index_location, props=None, props_from_file=None,
    kernel_cmdlines=None, setup_rootfs_from_kernel=None, ht_desc_to_setup=None,
    include_descriptors_from_image=None, signing_helper=None, signing_helper_with_files=None,
    release_string=header.release_string, append_to_release_string=None,
    required_libavb_version_minor=header.required_libavb_version_minor)
vbmeta = build/'vbmeta.img'
assert len(blob) <= (base/'vbmeta.img').stat().st_size
vbmeta.write_bytes(blob+b'\0'*((base/'vbmeta.img').stat().st_size-len(blob)))
_, new_header, new, _ = avb._parse_image(avbtool.ImageHandler(str(vbmeta), read_only=True))
assert avbtool.verify_vbmeta_signature(new_header, blob)
for field in ('flags', 'rollback_index', 'rollback_index_location', 'algorithm_type',
              'required_libavb_version_major', 'required_libavb_version_minor', 'release_string'):
    assert getattr(new_header, field) == getattr(header, field), field
assert len(old) == len(new)
assert sum(a.encode() != b.encode() for a, b in zip(old, new)) == 1
for a, b in zip(old, new):
    if a.encode() != b.encode():
        assert isinstance(a, avbtool.AvbHashtreeDescriptor) and a.partition_name == 'vendor'

destination.mkdir()
files = []
for partition, path in (('vendor', image), ('vbmeta', vbmeta)):
    name = partition+'.img'
    shutil.copyfile(path, destination/name)
    assert sha(destination/name) == sha(path)
    files.append(dict(partition=partition, name=name, bytes=path.stat().st_size, sha256=sha(path)))
report = dict(files=files, work_dir=str(build), base_revision='system-hardware-followup-sheng-r2',
    changed_vendor_files=sorted(changed), compiled_module_inputs={k: sha(v) for k, v in changes.items()},
    partition_sizes_unchanged=True, signatures_verified=True, readback_verified=True,
    all_vendor_inode_metadata_preserved=True, other_avb_descriptors_and_chain_preserved=True,
    single_canonical_sensor_init_verified=True, built_in_display_supported_hz=[60],
    first_commit_and_reboot_verified=False, runtime_verified=False)
(destination/'build-result.json').write_text(json.dumps(report, indent=2)+'\n')
(destination/'SHA256SUMS').write_text(''.join(f['sha256']+'  '+f['name']+'\n' for f in files))
(device/'docs/system-hardware-followup-r3.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
