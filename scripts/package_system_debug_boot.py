#!/usr/bin/env python3
"""Add Android's official debug ramdisk files to the installed OTA init_boot."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from extract_ota_boot_images import extract

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
product = rom / 'out/target/product/sheng'
destination = workspace / 'artifacts/boot-debug-sheng-lineage-24.0-r1'
assert not destination.exists(), 'Preserve previous debug artifacts'
assert shutil.disk_usage('/mnt/c').free > 20 * 1024**3
build = Path('/root/sheng-lineage/system-debug-boot') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
build.mkdir(parents=True)
images = extract()
base = Path(images['init_boot']['path'])
parts = build / 'parts'
unpack = rom / 'system/tools/mkbootimg/unpack_bootimg.py'
mkbootimg = rom / 'system/tools/mkbootimg/mkbootimg.py'
result = subprocess.run([sys.executable, str(unpack), '--boot_img', str(base), '--out', str(parts), '--format=mkbootimg'], check=True, capture_output=True, text=True)
arguments = shlex.split(result.stdout)
assert arguments[arguments.index('--header_version') + 1] == '4'
assert (parts / 'kernel').stat().st_size == 0 and (parts / 'ramdisk').stat().st_size > 0
root = build / 'root'
root.mkdir()
archive = subprocess.run(['lz4', '-dc', str(parts / 'ramdisk')], check=True, capture_output=True).stdout
subprocess.run(['cpio', '-idmu', '--no-absolute-filenames'], cwd=root, input=archive, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
before = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob('*') if path.is_file() and not path.is_symlink()}
debug = product / 'debug_ramdisk'
added = {}
for name in ('force_debuggable', 'adb_debug.prop', 'userdebug_plat_sepolicy.cil'):
    source = debug / name
    assert source.is_file() and not (root / name).exists()
    shutil.copyfile(source, root / name)
    (root / name).chmod(0o644)
    added[name] = hashlib.sha256(source.read_bytes()).hexdigest()
assert 'ro.adb.secure=0' in (root / 'adb_debug.prop').read_text()
assert 'ro.debuggable=1' in (root / 'adb_debug.prop').read_text()
assert 'ro.force.debuggable=1' in (root / 'adb_debug.prop').read_text()
cpio = subprocess.run([str(rom / 'out/host/linux-x86/bin/mkbootfs'), '-d', str(product), str(root)], check=True, capture_output=True).stdout
ramdisk = build / 'ramdisk.lz4'
ramdisk.write_bytes(subprocess.run(['lz4', '-l', '-12', '-c'], input=cpio, check=True, capture_output=True).stdout)
arguments[arguments.index('--ramdisk') + 1] = str(ramdisk)
image = build / 'init_boot.img'
subprocess.run([sys.executable, str(mkbootimg), *arguments, '--output', str(image)], check=True)
avbtool = rom / 'out/host/linux-x86/bin/avbtool'
subprocess.run([str(avbtool), 'add_hash_footer', '--image', str(image), '--partition_name', 'init_boot', '--partition_size', '8388608', '--algorithm', 'SHA256_RSA4096', '--key', str(rom / 'external/avb/test/data/testkey_rsa4096.pem')], check=True)
subprocess.run([str(avbtool), 'verify_image', '--image', str(image)], check=True, capture_output=True)
verified_parts = build / 'verified-parts'
subprocess.run([sys.executable, str(unpack), '--boot_img', str(image), '--out', str(verified_parts)], check=True, stdout=subprocess.DEVNULL)
verified_root = build / 'verified-root'
verified_root.mkdir()
archive = subprocess.run(['lz4', '-dc', str(verified_parts / 'ramdisk')], check=True, capture_output=True).stdout
subprocess.run(['cpio', '-idmu', '--no-absolute-filenames'], cwd=verified_root, input=archive, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
for name, expected in before.items():
    assert hashlib.sha256((verified_root / name).read_bytes()).hexdigest() == expected
for name, expected in added.items():
    assert hashlib.sha256((verified_root / name).read_bytes()).hexdigest() == expected
destination.mkdir()
target = destination / 'lineage-24.0-sheng-init_boot-debug-r1.img'
shutil.copyfile(image, target)
report = {'image': target.name, 'bytes': target.stat().st_size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
          'base': images['init_boot'], 'work_dir': str(build), 'added_official_debug_files': added,
          'all_original_ramdisk_files_unchanged': True, 'avb_verified': True, 'embedded_files_readback_verified': True,
          'purpose': 'Android official unlocked-device debug ramdisk: ADB/root for system boot diagnosis',
          'kernel_boot_vendor_boot_unchanged': True, 'new_image_hardware_tested': False}
(destination / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(destination / 'SHA256SUMS').write_text(report['sha256'] + '  ' + target.name + '\n')
(workspace / 'reports/system-debug-boot-r1.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
