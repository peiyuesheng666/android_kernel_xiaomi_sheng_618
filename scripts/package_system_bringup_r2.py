#!/usr/bin/env python3
"""Build targeted vendor/ODM images, retaining sizes and every AVB descriptor."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

from extract_ota_boot_images import extract, sha256_file

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
product = rom / 'out/target/product/sheng'
host = rom / 'out/host/linux-x86/bin'
build = Path('/root/sheng-lineage/system-bringup-r2')
build.mkdir(exist_ok=True)
destination = workspace / 'artifacts/system-bringup-sheng-r2'
destination.mkdir(exist_ok=True)
manifest = json.loads((workspace / 'reports/ota-install-manifest-audit.json').read_text())
partitions = {item['name']: item for item in manifest['partitions']}
environment = dict(os.environ)
environment['PATH'] = str(host) + ':' + environment['PATH']

def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)

def tree(root):
    result = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            result[str(path.relative_to(root))] = ('link', os.readlink(path))
        elif path.is_file():
            stat = path.stat()
            result[str(path.relative_to(root))] = ('file', sha256_file(path), stat.st_uid,
                                                 stat.st_gid, stat.st_mode & 0o7777)
    return result

base_vendor = Path(extract(('vendor',))['vendor']['path'])
assert sha256_file(base_vendor) == partitions['vendor']['sha256']
base_odm = workspace / 'artifacts/system-display-fix-sheng-lineage-24.0-r1/odm.img'
assert sha256_file(base_odm) == 'f0cf462d4ffc4193fa2c6f426ec4635d19d7553cdc13ecfaa770630ed2ad84d1'
base_vbmeta = workspace / 'artifacts/system-display-fix-sheng-lineage-24.0-r1/vbmeta-chain-fixed.img'
assert sha256_file(base_vbmeta) == 'f0a9d448f68ee32a09e3597750089e4c8334f23b4cc42a977ee72768fdd76ed5'
sources = workspace / 'device/xiaomi/sheng'
stock_audio = Path('/root/sheng-lineage/firmware-dump/partitions/odm/etc/audio/sku_kalama')
service_files = ('vendor.qti.hardware.display.allocator-service',
                 'vendor.qti.hardware.display.composer-service',
                 'android.hardware.sensors-service.xiaomi-multihal')
changes = {'vendor': {}, 'odm': {}}
for name in service_files:
    changes['vendor']['bin/hw/' + name] = product / 'vendor/bin/hw' / name
for name in ('vendor_sepolicy.cil', 'vendor_file_contexts'):
    changes['vendor']['etc/selinux/' + name] = product / 'vendor/etc/selinux' / name
changes['vendor'].update({
    'bin/sheng-touch-report': workspace / 'artifacts/system-touch-runtime-sheng-r1/touch_report',
    'usr/idc/NVTCapacitiveTouchScreen.idc': sources / 'configs/idc/NVTCapacitiveTouchScreen.idc',
    'etc/init/init.sheng.rc': sources / 'rootdir/etc/init.sheng.rc',
    'etc/audio/sku_kalama/resourcemanager_kalama_mtp.xml': stock_audio / 'resourcemanager_kalama_mtp.xml',
    'etc/audio/sku_kalama/mixer_paths_kalama_mtp.xml': workspace / 'artifacts/system-services-sheng-r2/mixer_paths_sheng.xml',
})
changes['odm'].update({
    'overlay/FrameworkResOverlaySheng.apk': workspace / 'artifacts/system-services-sheng-r2/FrameworkResOverlaySheng.apk',
    'etc/init/vendor.qti.camera.provider-service_64.rc': sources / 'rootdir/etc/vendor.qti.camera.provider-service_64.rc',
})
images = {}
for partition, base in (('vendor', base_vendor), ('odm', base_odm)):
    stage = build / partition
    if not stage.exists():
        run([host / 'fsck.erofs', '-d0', '--extract=' + str(stage), '--preserve', base],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    before = tree(stage)
    for relative, source in changes[partition].items():
        target = stage / relative
        assert target.parent.is_dir(), relative
        old_mode = target.stat().st_mode & 0o7777 if target.exists() else (
            0o755 if relative.startswith('bin/') else 0o644)
        old_uid = target.stat().st_uid if target.exists() else 0
        old_gid = target.stat().st_gid if target.exists() else 2000
        if relative.startswith('usr/idc/'):
            old_gid = 0
        if relative == 'etc/init/vendor.qti.camera.provider-service_64.rc':
            old_gid = 0
        shutil.copyfile(source, target)
        os.chmod(target, old_mode)
        os.chown(target, old_uid, old_gid)
    if partition == 'odm':
        props_path = stage / 'etc/build.prop'
        props = props_path.read_text()
        for key in ('vendor.display.idle_time', 'vendor.display.idle_time_inactive'):
            props = '\n'.join(line for line in props.splitlines() if not line.startswith(key + '=')) + '\n'
            props += '\n' + key + '=0\n'
        props_path.write_text(props)
    after = tree(stage)
    changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
    assert changed <= set(changes[partition]) | {'etc/build.prop'}, changed
    if partition == 'vendor' and not changed and (build / 'vendor.img').is_file():
        assert tree(stage) == tree(build / 'vendor-readback')
        run([host / 'avbtool', 'verify_image', '--image', build / 'vendor.img'], capture_output=True)
        images[partition] = build / 'vendor.img'
        continue
    packaging = product / 'obj/PACKAGING' / (partition + '_intermediates')
    original_config = product / ('obj/PACKAGING/target_files_intermediates/'
                                'lineage_sheng-target_files/META/' + partition + '_filesystem_config.txt')
    config_text = original_config.read_text()
    for relative in changes[partition]:
        full = partition + '/' + relative
        if not any(line.startswith(full + ' ') for line in config_text.splitlines()):
            stat = (stage / relative).stat()
            config_text += f'{full} {stat.st_uid} {stat.st_gid} {stat.st_mode & 0o7777:o} capabilities=0x0\n'
    config = build / (partition + '_filesystem_config.txt')
    config.write_text(config_text)
    original_list = (packaging / 'file_list.txt').read_text().splitlines()
    file_list = build / (partition + '_file_list.txt')
    file_list.write_text('\n'.join(sorted(set(original_list) | set(changes[partition]))) + '\n')
    info = build / (partition + '_image_info.txt')
    info.write_text((packaging / (partition + '_image_info.txt')).read_text().rstrip() +
                    '\nuse_dynamic_partition_size=false\n' + partition + '_size=' +
                    str(partitions[partition]['bytes']) + '\nfs_config=' + str(config) + '\n')
    image = build / (partition + '.img')
    with (build / (partition + '-build.log')).open('w') as output:
        run([host / 'build_image', '--input-directory-filter-file', file_list,
             stage, info, image, product / 'system'], cwd=rom, env=environment,
            stdout=output, stderr=subprocess.STDOUT)
    assert image.stat().st_size == partitions[partition]['bytes']
    readback = build / (partition + '-readback')
    if readback.exists():
        assert readback.resolve().parent == build.resolve()
        readback.rename(build / (readback.name + '-previous-' + str(time.time_ns())))
    run([host / 'fsck.erofs', '-d0', '--extract=' + str(readback), '--preserve', image],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert tree(stage) == tree(readback), partition + ': content or ownership changed'
    run([host / 'avbtool', 'verify_image', '--image', image], capture_output=True)
    images[partition] = image

sys.path.insert(0, str(rom / 'external/avb'))
import avbtool as avb_module
avb = avb_module.Avb()
_, header, old_descriptors, _ = avb._parse_image(avb_module.ImageHandler(str(base_vbmeta), read_only=True))
replacements = {}
for partition, image in images.items():
    _, _, descriptors, _ = avb._parse_image(avb_module.ImageHandler(str(image), read_only=True))
    matching = [item for item in descriptors if isinstance(item, avb_module.AvbHashtreeDescriptor)
                and item.partition_name == partition]
    assert len(matching) == 1
    replacements[partition] = matching[0]
descriptors = [replacements.get(item.partition_name, item)
               if isinstance(item, avb_module.AvbHashtreeDescriptor) else item for item in old_descriptors]
blob = avb._generate_vbmeta_blob(
    algorithm_name='SHA256_RSA4096', key_path=str(rom / 'external/avb/test/data/testkey_rsa4096.pem'),
    public_key_metadata_path=None, descriptors=descriptors, chain_partitions_use_ab=None,
    chain_partitions_do_not_use_ab=None, rollback_index=header.rollback_index, flags=header.flags,
    rollback_index_location=header.rollback_index_location, props=None, props_from_file=None,
    kernel_cmdlines=None, setup_rootfs_from_kernel=None, ht_desc_to_setup=None,
    include_descriptors_from_image=None, signing_helper=None, signing_helper_with_files=None,
    release_string=header.release_string, append_to_release_string=None,
    required_libavb_version_minor=header.required_libavb_version_minor)
vbmeta = build / 'vbmeta.img'
assert len(blob) <= partitions['vbmeta']['bytes']
vbmeta.write_bytes(blob + b'\0' * (partitions['vbmeta']['bytes'] - len(blob)))
_, new_header, new_descriptors, _ = avb._parse_image(avb_module.ImageHandler(str(vbmeta), read_only=True))
assert header.flags == new_header.flags == 3
assert avb_module.verify_vbmeta_signature(new_header, blob)
assert len(old_descriptors) == len(new_descriptors)
for old, new in zip(old_descriptors, new_descriptors):
    if old.encode() != new.encode():
        assert isinstance(old, avb_module.AvbHashtreeDescriptor) and old.partition_name in images
assert any(isinstance(item, avb_module.AvbChainPartitionDescriptor) and
           item.partition_name == 'vbmeta_system' for item in new_descriptors)
images['vbmeta'] = vbmeta
files = []
for partition, image in images.items():
    target = destination / image.name
    shutil.copyfile(image, target)
    assert sha256_file(image) == sha256_file(target)
    files.append({'partition': partition, 'name': image.name, 'bytes': image.stat().st_size,
                  'sha256': sha256_file(target)})
report = {'files': files, 'work_dir': str(build),
          'changed_files': {name: list(values) for name, values in changes.items()},
          'unchanged_partition_sizes': True, 'readback_content_and_ownership_verified': True,
          'avb_signatures_verified': True, 'all_original_chain_descriptors_preserved': True,
          'hardware_boot_tested': False}
(destination / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(workspace / 'reports/system-bringup-r2.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
