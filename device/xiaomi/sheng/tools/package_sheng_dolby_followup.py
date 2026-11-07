#!/usr/bin/env python3
"""Package device-built Dolby/rotation deltas over the verified installed r4.

This optional development helper never flashes or changes the ROM checkout.
Normal ROM builds install these modules through this device's product rules.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
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
parser = argparse.ArgumentParser()
parser.add_argument('--revision', type=int, default=5)
args = parser.parse_args()
assert args.revision >= 5
destination = workspace/f'artifacts/system-hardware-followup-sheng-r{args.revision}'
assert not destination.exists(), 'Never overwrite a built/flashed revision.'
build = Path('/root/sheng-lineage/hardware-followup')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
build.mkdir(parents=True)
environment = dict(os.environ, PATH=str(host)+':'+os.environ['PATH'], LANG='C.UTF-8', LC_ALL='C.UTF-8')

def run(arguments, **kwargs):
    return subprocess.run(list(map(str, arguments)), check=True, env=environment, **kwargs)

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def contents(root):
    return {str(path.relative_to(root)): ('link', os.readlink(path)) if path.is_symlink()
            else ('file', sha(path)) for path in root.rglob('*') if path.is_file() or path.is_symlink()}

bases = {
    'vendor': workspace/'artifacts/system-hardware-followup-sheng-r4/vendor.img',
    'vbmeta': workspace/'artifacts/system-hardware-followup-sheng-r4/vbmeta.img',
    'odm': workspace/'artifacts/system-hardware-followup-sheng-r2/odm.img',
    'system_ext': workspace/'artifacts/system-hardware-followup-sheng-r2/system_ext.img',
    'vbmeta_system': workspace/'artifacts/system-hardware-followup-sheng-r2/vbmeta_system.img',
}
expected = {
    'vendor': '0982fd68ff6cfc40e11ef338a62b9468e415236a7e31692740af3acd5ee6cece',
    'vbmeta': '5ceb8b1e2f9fadda1935f7d8bc1c5410eddc64f839b73a972a0b99c3248fd3ff',
    'odm': '9f8cbc7ee5603773a1d7d0b603027d921e5d06a95e4f3fa8fbcf91fe636367ab',
    'system_ext': '6fc35a1aaf69450f9540ae4d297b2b643dfef9801eeda98ba2bf4bb334a47916',
    'vbmeta_system': '56a22ad46eb3eaeb39bfcefa144c63b2a531a975d77ff6513beca4cd6dc450a7',
}
for partition, path in bases.items():
    assert sha(path) == expected[partition], partition

contexts = rom/'out/soong/.intermediates/system/sepolicy/file_contexts.concat.tmp/android_common/gen/file_contexts.concat.tmp'
run([host/'sefcontext_compile', '-o', build/'file_contexts.bin', contexts])

def update_properties(target, compiled, keys):
    values = dict(line.split('=', 1) for line in compiled.read_text().splitlines()
                  if line and not line.startswith('#') and '=' in line)
    assert all(key in values for key in keys), keys
    old = target.read_text().splitlines()
    result = [line for line in old if line.split('=', 1)[0] not in keys]
    result.extend(key+'='+values[key] for key in sorted(keys))
    target.write_text('\n'.join(result)+'\n')

def filesystem_config(partition, inodes, extra=()):
    entries = []
    for relative, inode in sorted(inodes.items()):
        capability = 0
        raw = inode['xattrs'].get('6:capability')
        if raw:
            fields = struct.unpack('<5I', bytes.fromhex(raw))
            assert fields[0] == 0x02000001 and fields[2] == fields[4] == 0
            capability = fields[1] | (fields[3] << 32)
        name = partition+relative if relative else ''
        entries.append(f"{name} {inode['uid']} {inode['gid']} {inode['mode']:o} capabilities=0x{capability:x}")
    entries.extend(extra)
    result = build/(partition+'_filesystem_config.txt')
    result.write_text('\n'.join(entries)+'\n')
    return result

def build_image(partition, stage, size, fs_config=None):
    props = dict(line.split('=', 1) for line in
            (product/'obj/PACKAGING'/(partition+'_intermediates')/(partition+'_image_info.txt')).read_text().splitlines()
            if '=' in line)
    props.update(use_dynamic_partition_size='false', **{partition+'_size': str(size)})
    if fs_config:
        props['fs_config'] = str(fs_config)
        props[partition+'_selinux_fc'] = str(build/'file_contexts.bin')
    info = build/(partition+'_image_info.txt')
    info.write_text('\n'.join(key+'='+value for key, value in props.items())+'\n')
    files = build/(partition+'_file_list.txt')
    files.write_text('\n'.join(sorted(str(path.relative_to(stage)) for path in stage.rglob('*')))+'\n')
    image = build/(partition+'.img')
    with (build/(partition+'-build.log')).open('w') as log:
        run([host/'build_image', '--input-directory-filter-file', files, stage, info, image, product/'system'],
            cwd=rom, stdout=log, stderr=subprocess.STDOUT)
    run([host/'avbtool', 'verify_image', '--image', image], capture_output=True)
    return image

changes = {}
images = {}
for partition in ('vendor', 'odm'):
    stage = build/partition
    run([host/'fsck.erofs', '-d0', '--extract='+str(stage), '--preserve', bases[partition]],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    before = contents(stage)
    inodes = metadata(bases[partition])
    if partition == 'vendor':
        sources = {relative: product/'vendor'/relative for relative in (
            'lib64/libar-pal.so', 'lib64/hw/audio.primary.sheng.so',
            'lib64/libdlbpreg.so', 'lib64/soundfx/libdlbvol.so',
            'lib64/libdlbdsservice.so', 'lib64/soundfx/libhwdap.so',
            'lib64/hw/libshgdolby_foundation.so',
            'etc/selinux/vendor_sepolicy.cil', 'etc/selinux/vendor_file_contexts',
        )}
        for relative in ('etc/audio/sku_kalama/audio_effects.xml', 'etc/audio_effects.xml'):
            sources[relative] = device/'configs/audio/sku_kalama/audio_effects.xml'
        preferred = list((rom/'out/soong/.intermediates/device/xiaomi/sheng/interfaces/audio/pal/libar-pal-sheng').glob('android_vendor_*_shared/libar-pal.so'))
        assert len(preferred) == 1 and sha(preferred[0]) == sha(sources['lib64/libar-pal.so'])
        assert (stage/'lib64/hw/audio.primary.kalama.so').is_file()
        update_properties(stage/'build.prop', product/'vendor/build.prop', {
            'ro.audio.monitorRotation', 'ro.hardware.audio.primary',
            'vendor.audio.sheng.stereo_quad_coeff', 'vendor.audio.sheng.offload_quad_coeff',
            'vendor.audio.sheng.dap_native_quad',
        })
        extra = ['vendor/lib64/hw/audio.primary.sheng.so 0 0 644 capabilities=0x0']
        assert '/lib64/hw/audio.primary.sheng.so' not in inodes
        property_path = 'build.prop'
    else:
        sources = {'etc/selinux/precompiled_sepolicy': product/'odm/etc/selinux/precompiled_sepolicy'}
        for component in ('plat', 'system_ext', 'product'):
            relative = f'etc/selinux/precompiled_sepolicy.{component}_sepolicy_and_mapping.sha256'
            assert (stage/relative).read_bytes() == (product/'odm'/relative).read_bytes(), relative
        update_properties(stage/'etc/build.prop', product/'odm/etc/build.prop', {'ro.vendor.audio.adsp.spatial'})
        extra = []
        property_path = 'etc/build.prop'
    for relative, source in sources.items():
        assert source.is_file(), source
        target = stage/relative
        assert target.parent.is_dir()
        shutil.copyfile(source, target)
        if relative == 'lib64/hw/audio.primary.sheng.so': target.chmod(0o644)
    after = contents(stage)
    changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
    assert changed <= set(sources) | {property_path}, changed
    config = filesystem_config(partition, inodes, extra)
    image = build_image(partition, stage, bases[partition].stat().st_size, config)
    assert image.stat().st_size == bases[partition].stat().st_size
    readback = build/(partition+'-readback')
    run([host/'fsck.erofs', '-d0', '--extract='+str(readback), '--preserve', image],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert contents(readback) == after
    new_inodes = metadata(image)
    assert all(new_inodes[name] == inode for name, inode in inodes.items()), partition
    if extra:
        added = new_inodes['/lib64/hw/audio.primary.sheng.so']
        assert added['uid'] == added['gid'] == 0 and added['mode'] == 0o644
        assert bytes.fromhex(added['xattrs']['6:selinux']).rstrip(b'\0') == b'u:object_r:vendor_file:s0'
    changes[partition] = sorted(changed)
    images[partition] = image

raw = build/'system_ext-base.raw.img'
run([host/'simg2img', bases['system_ext'], raw])
system = build/'system_ext'
system.mkdir()
run(['debugfs', '-R', 'rdump / '+str(system), raw], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
before = contents(system)
apk_relative = 'priv-app/ShengDolby/ShengDolby.apk'
apk = product/'system_ext'/apk_relative
def certificates(path):
    result = run([rom/'prebuilts/jdk/jdk21/linux-x86/bin/java', '-jar',
            rom/'prebuilts/sdk/tools/linux/lib/apksigner.jar', 'verify', '--print-certs', path],
            cwd=rom, capture_output=True, text=True)
    values = sorted(line.split(':', 1)[1].strip() for line in result.stdout.splitlines()
                    if 'certificate SHA-256 digest:' in line)
    assert values
    return values
assert certificates(apk) == certificates(system/apk_relative)
shutil.copyfile(apk, system/apk_relative)
after = contents(system)
assert {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)} <= {apk_relative}
images['system_ext'] = build_image('system_ext', system, raw.stat().st_size)
new_raw = build/'system_ext.raw.img'
run([host/'simg2img', images['system_ext'], new_raw])
assert new_raw.stat().st_size == raw.stat().st_size
readback = build/'system_ext-readback'
readback.mkdir()
run(['debugfs', '-R', 'rdump / '+str(readback), new_raw], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
assert contents(readback) == after
changes['system_ext'] = [apk_relative]

sys.path.insert(0, str(rom/'external/avb'))
import avbtool
avb = avbtool.Avb()
def update_vbmeta(base, partitions, output, bits):
    _, header, old, _ = avb._parse_image(avbtool.ImageHandler(str(base), read_only=True))
    replacements = {}
    for partition in partitions:
        _, _, embedded, _ = avb._parse_image(avbtool.ImageHandler(str(images[partition]), read_only=True))
        selected = [d for d in embedded if isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == partition]
        assert len(selected) == 1
        replacements[partition] = selected[0]
    descriptors = [replacements.get(d.partition_name, d) if isinstance(d, avbtool.AvbHashtreeDescriptor)
                   else d for d in old]
    assert all(sum(isinstance(d, avbtool.AvbHashtreeDescriptor) and d.partition_name == p for d in old) == 1
               for p in partitions)
    blob = avb._generate_vbmeta_blob(algorithm_name='SHA256_RSA'+str(bits),
        key_path=str(rom/f'external/avb/test/data/testkey_rsa{bits}.pem'),
        public_key_metadata_path=None, descriptors=descriptors, chain_partitions_use_ab=None,
        chain_partitions_do_not_use_ab=None, rollback_index=header.rollback_index, flags=header.flags,
        rollback_index_location=header.rollback_index_location, props=None, props_from_file=None,
        kernel_cmdlines=None, setup_rootfs_from_kernel=None, ht_desc_to_setup=None,
        include_descriptors_from_image=None, signing_helper=None, signing_helper_with_files=None,
        release_string=header.release_string, append_to_release_string=None,
        required_libavb_version_minor=header.required_libavb_version_minor)
    assert len(blob) <= base.stat().st_size
    output.write_bytes(blob+b'\0'*(base.stat().st_size-len(blob)))
    _, new_header, new, _ = avb._parse_image(avbtool.ImageHandler(str(output), read_only=True))
    assert avbtool.verify_vbmeta_signature(new_header, blob)
    for field in ('flags', 'rollback_index', 'rollback_index_location', 'algorithm_type',
                  'required_libavb_version_major', 'required_libavb_version_minor', 'release_string'):
        assert getattr(new_header, field) == getattr(header, field)
    assert len(old) == len(new)
    for previous, current in zip(old, new):
        if previous.encode() != current.encode():
            assert isinstance(previous, avbtool.AvbHashtreeDescriptor) and previous.partition_name in partitions
    return output
images['vbmeta'] = update_vbmeta(bases['vbmeta'], ('vendor', 'odm'), build/'vbmeta.img', 4096)
images['vbmeta_system'] = update_vbmeta(bases['vbmeta_system'], ('system_ext',), build/'vbmeta_system.img', 2048)

destination.mkdir()
files = []
for partition, path in images.items():
    shutil.copyfile(path, destination/(partition+'.img'))
    assert sha(destination/(partition+'.img')) == sha(path)
    files.append(dict(partition=partition, name=partition+'.img', bytes=path.stat().st_size, sha256=sha(path)))
report = dict(files=files, work_dir=str(build), changed_files=changes,
    verified_base_sha256=expected, readback_verified=True, signatures_verified=True,
    partition_sizes_unchanged=True, existing_erofs_inode_metadata_unchanged=True,
    unrelated_avb_descriptors_preserved=True, apk_certificate_preserved=True,
    installed_public_policy_ids_matched=True, native_device_pal_input_verified=True,
    hardware_boot_tested=False)
(destination/'build-result.json').write_text(json.dumps(report, indent=2)+'\n')
(destination/'SHA256SUMS').write_text(''.join(item['sha256']+'  '+item['name']+'\n' for item in files))
(device/f'docs/system-hardware-followup-r{args.revision}.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
