#!/usr/bin/env python3
"""Rebuild only system_ext with its missing Dolby allowlist and matching vbmeta."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from extract_ota_boot_images import extract

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
product = rom / 'out/target/product/sheng'
host = rom / 'out/host/linux-x86/bin'
destination = workspace / 'artifacts/system-boot-fix-sheng-lineage-24.0-r1'
assert not destination.exists()
assert shutil.disk_usage('/mnt/c').free > 20 * 1024**3
build = Path('/root/sheng-lineage/system-ext-permission-fix') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
build.mkdir(parents=True)
manifest = json.loads((workspace / 'reports/ota-install-manifest-audit.json').read_text())
partitions = {item['name']: item for item in manifest['partitions']}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


raw_base = Path(extract(('system_ext',))['system_ext']['path'])
assert raw_base.stat().st_size == partitions['system_ext']['bytes']
assert sha(raw_base) == partitions['system_ext']['sha256'], 'Staged image differs from the installed OTA'
relative = 'etc/permissions/privapp-permissions-org.lineageos.sheng.dolby.xml'
source = workspace / 'device/xiaomi/sheng/dolby/ShengDolby' / Path(relative).name
staging = build / 'system_ext'
staging.mkdir()
run(['debugfs', '-R', 'rdump / ' + str(staging), raw_base], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
assert not (staging / relative).exists()
shutil.copyfile(source, staging / relative)
(staging / relative).chmod(0o644)
packaging = product / 'obj/PACKAGING/system_ext_intermediates'
file_list = build / 'file_list.txt'
file_list.write_text((packaging / 'file_list.txt').read_text().rstrip() + '\n' + relative + '\n')
properties = build / 'system_ext_image_info.txt'
properties.write_text((packaging / 'system_ext_image_info.txt').read_text().rstrip() +
                      '\nsystem_ext_size=' + str(partitions['system_ext']['bytes']) + '\n')
environment = dict(os.environ)
environment['PATH'] = str(host) + ':' + environment['PATH']
image = build / 'system_ext.img'
with (build / 'build.log').open('w') as output:
    run([host / 'build_image', '--input-directory-filter-file', file_list, staging,
         properties, image, product / 'system'], cwd=rom, env=environment, stdout=output, stderr=subprocess.STDOUT)
raw = build / 'system_ext.raw.img'
run([host / 'simg2img', image, raw])
assert raw.stat().st_size == partitions['system_ext']['bytes'], 'Partition size changed'
embedded = run(['debugfs', '-R', 'cat /' + relative, raw], capture_output=True).stdout
assert embedded == source.read_bytes(), 'Allowlist readback failed'
apk_path = 'priv-app/ShengDolby/ShengDolby.apk'
embedded_apk = run(['debugfs', '-R', 'cat /' + apk_path, raw], capture_output=True).stdout
assert hashlib.sha256(embedded_apk).hexdigest() == sha(staging / apk_path)
avbtool = host / 'avbtool'
run([avbtool, 'verify_image', '--image', image], capture_output=True)
base_vbmeta = build / 'original-vbmeta_system.img'
base_data = Path(extract(('vbmeta_system',))['vbmeta_system']['path']).read_bytes()
assert hashlib.sha256(base_data).hexdigest() == partitions['vbmeta_system']['sha256']
base_vbmeta.write_bytes(base_data)
new_vbmeta = build / 'vbmeta_system.img'
run([avbtool, 'make_vbmeta_image', '--output', new_vbmeta, '--algorithm', 'SHA256_RSA2048',
     '--key', rom / 'external/avb/test/data/testkey_rsa2048.pem', '--rollback_index', '1',
     '--padding_size', '4096', '--include_descriptors_from_image', base_vbmeta,
     '--include_descriptors_from_image', image])
installed_images = extract(('product', 'system'))
for name in ('product', 'system'):
    (build / (name + '.img')).symlink_to(Path(installed_images[name]['path']))
run([avbtool, 'verify_image', '--image', new_vbmeta], capture_output=True)
old_info = run([avbtool, 'info_image', '--image', base_vbmeta], capture_output=True, text=True).stdout
new_info = run([avbtool, 'info_image', '--image', new_vbmeta], capture_output=True, text=True).stdout


def roots(info):
    return dict(re.findall(r'Partition Name:\s+(\S+).*?Root Digest:\s+(\S+)', info, re.S))


old_roots, new_roots = roots(old_info), roots(new_info)
assert set(old_roots) == set(new_roots) == {'system', 'product', 'system_ext'}
assert old_roots['system'] == new_roots['system'] and old_roots['product'] == new_roots['product']
assert old_roots['system_ext'] != new_roots['system_ext']
assert 'Public key (sha1):        cdbb77177f731920bbe0a0f94f84d9038ae0617d' in new_info
destination.mkdir()
files = []
for path in (image, new_vbmeta):
    shutil.copyfile(path, destination / path.name)
    assert sha(destination / path.name) == sha(path)
    files.append({'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha(path)})
report = {'files': files, 'work_dir': str(build), 'source': str(source), 'allowlist_sha256': sha(source),
          'only_added_staging_file': relative, 'base_matches_installed_ota': True,
          'partition_size_unchanged': raw.stat().st_size, 'allowlist_and_apk_readback_verified': True,
          'avb_image_and_vbmeta_verified': True, 'other_vbmeta_roots_unchanged': True,
          'hardware_boot_tested': False}
(destination / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(workspace / 'reports/system-ext-permission-fix-r1.json').write_text(json.dumps(report, indent=2) + '\n')
(destination / 'SHA256SUMS').write_text(''.join(item['sha256'] + '  ' + item['name'] + '\n' for item in files))
print(json.dumps(report, indent=2))
