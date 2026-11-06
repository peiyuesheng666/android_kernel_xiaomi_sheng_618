#!/usr/bin/env python3
"""Package freshly built device modules over the verified installed bases.

This development helper reads sources/build outputs and writes new images only.
Normal ROM/OTA builds use the device's Soong modules and product configuration.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
from audit_erofs_metadata import metadata as erofs_metadata

device = Path(__file__).resolve().parents[1]
workspace = device.parents[2]
rom = Path('/root/sheng-lineage/lineage-24.0')
product = rom/'out/target/product/sheng'
host = rom/'out/host/linux-x86/bin'
audio_base = workspace/'artifacts/system-audio-offload-sheng-r1'
system_base = workspace/'artifacts/system-boot-fix-sheng-lineage-24.0-r1'
odm_base = workspace/'artifacts/system-bringup-sheng-r2'
destination = workspace/'artifacts/system-hardware-followup-sheng-r2'
assert not destination.exists(), 'Never overwrite a built/flashed revision.'
build = Path('/root/sheng-lineage/hardware-followup')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
build.mkdir(parents=True)
environment = dict(os.environ, PATH=str(host)+':'+os.environ['PATH'])

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, env=environment, **kwargs)

def contents(root):
    entries = {}
    for path in root.rglob('*'):
        name = str(path.relative_to(root))
        if path.is_symlink(): entries[name] = ('link', os.readlink(path))
        elif path.is_file(): entries[name] = ('file', sha(path))
    return entries

def vendor_metadata(root):
    return {str(path.relative_to(root)): (path.lstat().st_uid, path.lstat().st_gid,
            path.lstat().st_mode & 0o7777,
            tuple((key, os.getxattr(path, key, follow_symlinks=False).hex())
                  for key in sorted(os.listxattr(path, follow_symlinks=False))))
            for path in root.rglob('*')}

for folder, expected in [
    (audio_base, {'vendor.img':'1fb562d742ac2921a95c0ad54d8761e3a4ece1334cdbfcdc54c25170e0941d3f',
                  'vbmeta.img':'aac43d3bb4a7b1a2db34ac7f29b0bd2feba5407401e54bcd4e50222ba2dcf1fa'}),
    (system_base, {'system_ext.img':'4135580582cd64cd75fc59eb4a4e547c8340174ee5703b3b1cab887d5f93a4a4',
                   'vbmeta_system.img':'de2ef601ac755772662dd9b8496bb78190af4f4ab8760c4f4fe078fc04cf5fa7'})]:
    for name, digest in expected.items(): assert sha(folder/name) == digest, name

vendor = build/'vendor'
run([host/'fsck.erofs', '-d0', '--extract='+str(vendor), '--preserve', audio_base/'vendor.img'],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
before_vendor = contents(vendor)
before_metadata = vendor_metadata(vendor)
changes = {
    relative: product/'vendor'/relative for relative in (
        'lib64/libar-pal.so',
        'lib64/hw/libshgdolby_foundation.so',
        'lib64/libdlbdsservice.so',
        'lib64/soundfx/libhwdap.so',
        'bin/hw/android.hardware.sensors-service.xiaomi-multihal',
        'bin/hw/vendor.qti.hardware.display.composer-service',
        'bin/hw/vendor.qti.hardware.display.allocator-service',
        'etc/selinux/vendor_file_contexts',
        'etc/selinux/vendor_sepolicy.cil',
    )
}
changes['etc/displayconfig/display_id_4630947038039379843.xml'] = device/'configs/displayconfig/display_id_4630947038039379843.xml'
expected_libs = {
    'libshgdolby_foundation.so':'97a7b4b29feb486a2f2cfd62ea289563129fee2a6be8ab9b6750a3f0ba2ea3c9',
    'libdlbdsservice.so':'8ebcb388211456a1650a2b1574fa75b8dbce1bbbd2d54e7a917238d936775441',
    'libhwdap.so':'6574b00b37c369a52323902b2a7cee8d433240cfa026d0930f90e08d8d49fd87',
}
for name, digest in expected_libs.items():
    relative = 'lib64/hw/'+name if name == 'libshgdolby_foundation.so' else ('lib64/soundfx/'+name if name == 'libhwdap.so' else 'lib64/'+name)
    assert sha(product/'vendor'/relative) == digest, relative
for relative, source in changes.items():
    target = vendor/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = target.stat().st_mode & 0o7777 if target.exists() else 0o644
    shutil.copyfile(source, target)
    os.chmod(target, mode)
    os.chown(target, 0, 0)
(vendor/'etc/displayconfig').chmod(0o755)
removed = [
    'bin/hw/vendor.qti.hardware.vibrator.service',
    'etc/init/vendor.qti.hardware.vibrator.service.rc',
    'etc/vintf/manifest/vendor.qti.hardware.vibrator.service.xml',
    'lib64/hw/vibrator.default.so',
]
for relative in removed:
    assert (vendor/relative).is_file(), relative
    (vendor/relative).unlink()
fc_line = r'/(vendor|system/vendor)/lib64/hw/libshgdolby_foundation\.so    u:object_r:vendor_file:s0'
vendor_fc = vendor/'etc/selinux/vendor_file_contexts'
assert fc_line in vendor_fc.read_text()
after_vendor = contents(vendor)
vendor_changed = {key for key in before_vendor.keys() | after_vendor.keys()
                  if before_vendor.get(key) != after_vendor.get(key)}
expected_vendor_changes = {key for key in changes if before_vendor.get(key) != after_vendor.get(key)} | set(removed)
assert vendor_changed == expected_vendor_changes, vendor_changed

# Compile the identical packaging contexts with one precise new-library rule.
# Other HAL labels, including graphics, remain unchanged.
combined = rom/'out/soong/.intermediates/system/sepolicy/file_contexts.concat.tmp/android_common/gen/file_contexts.concat.tmp'
fc = build/'file_contexts'
fc.write_text(combined.read_text())
assert fc_line in fc.read_text()
run([host/'sefcontext_compile', '-o', build/'file_contexts.bin', fc])
vendor_config = product/'obj/PACKAGING/target_files_intermediates/lineage_sheng-target_files/META/vendor_filesystem_config.txt'
config = build/'vendor_filesystem_config.txt'
config.write_text(vendor_config.read_text().rstrip()+'\n'+
    'vendor/etc/displayconfig 0 0 755 capabilities=0x0\n'+
    'vendor/etc/displayconfig/display_id_4630947038039379843.xml 0 0 644 capabilities=0x0\n'+
    'vendor/lib64/hw/libshgdolby_foundation.so 0 0 644 capabilities=0x0\n')

def build_image(partition, stage, size, fs_config=None, selinux_fc=None):
    packaging = product/'obj/PACKAGING'/(partition+'_intermediates')
    file_list = build/(partition+'_file_list.txt')
    file_list.write_text('\n'.join(sorted(str(p.relative_to(stage)) for p in stage.rglob('*')))+'\n')
    info = build/(partition+'_image_info.txt')
    props = dict(line.split('=', 1) for line in (packaging/(partition+'_image_info.txt')).read_text().splitlines() if '=' in line)
    props.update(use_dynamic_partition_size='false', **{partition+'_size':str(size)})
    if fs_config: props['fs_config'] = str(fs_config)
    if selinux_fc: props[partition+'_selinux_fc'] = str(selinux_fc)
    info.write_text('\n'.join(key+'='+value for key, value in props.items())+'\n')
    result = build/(partition+'.img')
    with (build/(partition+'-build.log')).open('w') as log:
        run([host/'build_image', '--input-directory-filter-file', file_list, stage, info, result, product/'system'],
            cwd=rom, stdout=log, stderr=subprocess.STDOUT)
    run([host/'avbtool', 'verify_image', '--image', result], capture_output=True)
    return result

new_vendor = build_image('vendor', vendor, (audio_base/'vendor.img').stat().st_size, config, build/'file_contexts.bin')
assert new_vendor.stat().st_size == (audio_base/'vendor.img').stat().st_size
readback_vendor = build/'vendor-readback'
run([host/'fsck.erofs', '-d0', '--extract='+str(readback_vendor), '--preserve', new_vendor],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
assert contents(readback_vendor) == after_vendor
after_metadata = vendor_metadata(readback_vendor)
metadata_changed = {key for key in before_metadata.keys() & after_metadata.keys()
                    if before_metadata[key] != after_metadata[key]}
assert metadata_changed <= vendor_changed, metadata_changed
original_inode_metadata = erofs_metadata(audio_base/'vendor.img')
new_inode_metadata = erofs_metadata(new_vendor)
inode_metadata_changed = {key for key in original_inode_metadata.keys() & new_inode_metadata.keys()
                          if original_inode_metadata[key] != new_inode_metadata[key]}
assert inode_metadata_changed <= {'/'+key for key in vendor_changed}, inode_metadata_changed
foundation_label = bytes.fromhex(new_inode_metadata['/lib64/hw/libshgdolby_foundation.so']['xattrs']['6:selinux'])
assert foundation_label.rstrip(b'\0') == b'u:object_r:vendor_file:s0'

raw_base = build/'system_ext-base.raw.img'
run([host/'simg2img', system_base/'system_ext.img', raw_base])
assert raw_base.stat().st_size == 572813312
system_ext = build/'system_ext'
system_ext.mkdir()
run(['debugfs', '-R', 'rdump / '+str(system_ext), raw_base], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
before_system = contents(system_ext)
apk = product/'system_ext/priv-app/ShengDolby/ShengDolby.apk'
apk_path = 'priv-app/ShengDolby/ShengDolby.apk'
shutil.copyfile(apk, system_ext/apk_path)
(system_ext/apk_path).chmod(0o644)
after_system = contents(system_ext)
system_changed = {key for key in before_system.keys() | after_system.keys()
                  if before_system.get(key) != after_system.get(key)}
assert system_changed == {apk_path}, system_changed
new_system = build_image('system_ext', system_ext, raw_base.stat().st_size)
system_raw = build/'system_ext.raw.img'
run([host/'simg2img', new_system, system_raw])
assert system_raw.stat().st_size == raw_base.stat().st_size
system_readback = build/'system_ext-readback'
system_readback.mkdir()
run(['debugfs', '-R', 'rdump / '+str(system_readback), system_raw], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
assert contents(system_readback) == after_system

# The cover default is a device-specific framework RRO installed on ODM.
odm_image = odm_base/'odm.img'
assert sha(odm_image) == '380aac5b18d5573a8389847553ffcdfdbbf8422413548daddd3389f5bcc76b6d'
odm = build/'odm'
run([host/'fsck.erofs', '-d0', '--extract='+str(odm), '--preserve', odm_image],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
before_odm = contents(odm)
overlay = 'overlay/FrameworkResOverlaySheng.apk'
shutil.copyfile(product/'odm'/overlay, odm/overlay)
(odm/overlay).chmod(0o644)
after_odm = contents(odm)
odm_changed = {key for key in before_odm.keys() | after_odm.keys()
               if before_odm.get(key) != after_odm.get(key)}
assert odm_changed == {overlay}
new_odm = build_image('odm', odm, odm_image.stat().st_size)
assert new_odm.stat().st_size == odm_image.stat().st_size
odm_readback = build/'odm-readback'
run([host/'fsck.erofs', '-d0', '--extract='+str(odm_readback), '--preserve', new_odm],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
assert contents(odm_readback) == after_odm
original_odm_metadata, new_odm_metadata = erofs_metadata(odm_image), erofs_metadata(new_odm)
odm_metadata_changed = {key for key in original_odm_metadata.keys() & new_odm_metadata.keys()
    if original_odm_metadata[key] != new_odm_metadata[key]}
assert odm_metadata_changed <= {'/'+overlay}, odm_metadata_changed

sys.path.insert(0, str(rom/'external/avb'))
import avbtool
avb = avbtool.Avb()
def replace_vbmeta(base, image, partition, output, algorithm, key):
    _, header, old, _ = avb._parse_image(avbtool.ImageHandler(str(base), read_only=True))
    _, _, embedded, _ = avb._parse_image(avbtool.ImageHandler(str(image), read_only=True))
    updated = [item for item in embedded if isinstance(item, avbtool.AvbHashtreeDescriptor) and item.partition_name == partition]
    assert len(updated) == 1
    descriptors = [updated[0] if isinstance(item, avbtool.AvbHashtreeDescriptor) and item.partition_name == partition else item for item in old]
    blob = avb._generate_vbmeta_blob(algorithm_name=algorithm, key_path=str(key),
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
    assert new_header.flags == header.flags and new_header.rollback_index == header.rollback_index
    assert len(old) == len(new)
    for previous, current in zip(old, new):
        if previous.encode() != current.encode():
            assert isinstance(previous, avbtool.AvbHashtreeDescriptor) and previous.partition_name == partition
    return output
new_vbmeta = replace_vbmeta(audio_base/'vbmeta.img', new_vendor, 'vendor', build/'vbmeta.img',
    'SHA256_RSA4096', rom/'external/avb/test/data/testkey_rsa4096.pem')
new_vbmeta = replace_vbmeta(new_vbmeta, new_odm, 'odm', build/'vbmeta-with-odm.img',
    'SHA256_RSA4096', rom/'external/avb/test/data/testkey_rsa4096.pem')
new_system_vbmeta = replace_vbmeta(system_base/'vbmeta_system.img', new_system, 'system_ext', build/'vbmeta_system.img',
    'SHA256_RSA2048', rom/'external/avb/test/data/testkey_rsa2048.pem')
destination.mkdir()
files = []
for partition, path in [('vendor', new_vendor), ('odm', new_odm), ('system_ext', new_system), ('vbmeta', new_vbmeta), ('vbmeta_system', new_system_vbmeta)]:
    filename = partition+'.img'
    shutil.copyfile(path, destination/filename)
    assert sha(destination/filename) == sha(path)
    files.append(dict(partition=partition, name=filename, bytes=path.stat().st_size, sha256=sha(path)))
report = dict(files=files, work_dir=str(build), changed_vendor_files=sorted(vendor_changed),
    changed_system_ext_files=sorted(system_changed), removed_fake_vibrator_files=removed,
    changed_odm_files=sorted(odm_changed), partition_sizes_unchanged=True, signatures_verified=True,
    other_avb_descriptors_and_chain_preserved=True, readback_verified=True,
    unrelated_vendor_metadata_unchanged=True, unrelated_odm_metadata_unchanged=True,
    compiled_module_inputs={key: sha(value) for key, value in changes.items()},
    hardware_boot_tested=False)
(destination/'build-result.json').write_text(json.dumps(report, indent=2)+'\n')
(destination/'SHA256SUMS').write_text(''.join(item['sha256']+'  '+item['name']+'\n' for item in files))
(device/'docs/system-hardware-followup-r2.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
