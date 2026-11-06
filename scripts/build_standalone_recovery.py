#!/usr/bin/env python3
"""Package our compiled Lineage recovery with this tablet's exact stock BSP."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
hardware = Path('/root/sheng-lineage/firmware-dump/hardware')
product = rom / 'out/target/product/sheng'
build = Path('/root/sheng-lineage/recovery-r2') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
destination = work / 'artifacts/recovery-sheng-lineage-24.0-r2'
configuration = work / 'device/xiaomi/sheng/recovery'
config = json.loads((configuration / 'standalone.json').read_text())
commands = []


def run(args, **kwargs):
    args = list(map(str, args))
    commands.append(args)
    result = subprocess.run(args, **kwargs)
    if result.returncode:
        detail = result.stderr or ''
        if isinstance(detail, bytes):
            detail = detail.decode(errors='replace')
        raise RuntimeError(f'{args[0]} exited {result.returncode}: {detail[-4000:]}')
    return result


def digest(file):
    value = hashlib.sha256()
    with file.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


assert shutil.disk_usage('/mnt/c').free > 20 * 1024**3
receipt = json.loads((work / 'artifacts/lineage-24.0-20261105-UNOFFICIAL-sheng/build-result.json').read_text())
assert receipt['compiled'] and not receipt['hardware_boot_tested']
# Start from the exact userspace already exported, not a possibly stale staging
# directory. The official unpacker and cpio reconstruct modes and symlinks.
old_recovery = work / 'artifacts/lineage-24.0-20261105-UNOFFICIAL-sheng/recovery.img'
expected = next(item['sha256'] for item in receipt['files'] if item['name'] == 'recovery.img')
assert digest(old_recovery) == expected
assert not build.exists(), f'Use a fresh build directory, preserving evidence: {build}'
build.mkdir(parents=True)
destination.mkdir(parents=True, exist_ok=True)
unpacked = build / 'input'
run([sys.executable, rom / 'system/tools/mkbootimg/unpack_bootimg.py',
     '--boot_img', old_recovery, '--out', unpacked], stdout=subprocess.DEVNULL)
root = build / 'root'
root.mkdir()
archive = run(['lz4', '-dc', unpacked / 'ramdisk'], capture_output=True).stdout
run(['cpio', '-idmu', '--no-absolute-filenames'], cwd=root, input=archive,
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
# The source kernel is under investigation after the user's boot failure.
# Extract the stock kernel from our immutable local firmware copy instead.
stock_boot = build / 'stock-boot'
run([sys.executable, rom / 'system/tools/mkbootimg/unpack_bootimg.py',
     '--boot_img', hardware / 'boot-images/boot.img', '--out', stock_boot],
    stdout=subprocess.DEVNULL)
originals = json.loads((work / 'reports/stock-boot.json').read_text())
assert digest(hardware / 'boot-images/boot.img') == originals['boot']['sha256']
kernel = stock_boot / 'kernel'
banner = re.search(rb'Linux version (5\.15\.178-\S+)', kernel.read_bytes())
assert banner and banner[1].startswith(b'5.15.178-android13-8-')
release = banner[1].decode()
kernel_gz = build / 'Image.gz'
with kernel_gz.open('wb') as raw:
    with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed:
        compressed.write(kernel.read_bytes())

plan = json.loads((work / 'device/xiaomi/sheng/kernel/stock-modules/module-plan.json').read_text())
stock_receipt = json.loads((work / 'reports/stock-all-module-abi.json').read_text())['closure_inputs']
selected = plan['recovery_modules']
stock_inputs = {}
for file in sorted((hardware / 'modules').rglob('*.ko')):
    if file.name in stock_inputs:
        assert digest(file) == digest(stock_inputs[file.name]), file.name
    else:
        stock_inputs[file.name] = file
assert all(name in stock_inputs for name in selected)
# Replace the whole module directory. Never retain source-built swap modules
# alongside the stock kernel or rely on installed vendor ramdisk metadata.
modules = root / 'lib/modules'
assert modules.resolve().is_relative_to(root.resolve()) and not modules.is_symlink()
shutil.rmtree(modules)
versioned = modules / release
versioned.mkdir(parents=True)
module_hashes = {}
for name in selected:
    source = stock_inputs[name]
    assert digest(source) == stock_receipt[name]['sha256']
    if name in plan['stock_modules_sha256']:
        assert digest(source) == plan['stock_modules_sha256'][name]
    shutil.copyfile(source, versioned / name)
    os.chmod(versioned / name, 0o644)
    module_hashes[name] = digest(source)
run(['depmod', '-b', root, release], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
loads = (work / 'device/xiaomi/sheng/configs/modules/modules.load.recovery').read_text()
for name in ('modules.load', 'modules.load.recovery'):
    (versioned / name).write_text(loads)
dep_text = (versioned / 'modules.dep').read_text()
indexed = {line.split(':', 1)[0] for line in dep_text.splitlines()}
assert set(selected) <= indexed
assert all(Path(name).name in selected for name in loads.splitlines() if name.strip())
run(['modprobe', '--dry-run', '--all', '--verbose', '--dirname', root,
     '--set-version', release, *[line.removesuffix('.ko') for line in loads.splitlines() if line.strip()]],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# The existing qcom recovery module is in /system/etc/init, which init parses
# itself. Replace its contents once instead of importing it twice at root.
shutil.copyfile(configuration / 'init.recovery.sheng.rc', root / 'system/etc/init/init.recovery.qcom.rc')
shutil.copyfile(configuration / 'hardware.sh', root / 'system/bin/sheng-recovery-hardware')
os.chmod(root / 'system/bin/sheng-recovery-hardware', 0o755)
firmware = root / 'lib/firmware'
firmware.mkdir(exist_ok=True)
for name in ('novatek_nt36532_n81a_fw_csot.bin', 'novatek_nt36532_n81a_mp_csot.bin',
             'n81a_nova_thp_config.ini'):
    source = rom / 'vendor/xiaomi/sheng/proprietary/odm/firmware' / name
    shutil.copyfile(source, firmware / name)

# Explicitly carry recovery mode in the self-contained ramdisk; no generic
# init_boot ramdisk is concatenated to this legacy image.
properties = root / 'prop.default'
with properties.open('a') as stream:
    stream.write('\n# sheng standalone recovery bringup\nro.sheng.recovery.revision=r2\n')
cpio_file = build / 'ramdisk.cpio'
with cpio_file.open('wb') as stream:
    run([rom / 'out/host/linux-x86/bin/mkbootfs', '-d', product, root], stdout=stream)
ramdisk = build / 'ramdisk.lz4'
run(['lz4', '-l', '-12', '-f', cpio_file, ramdisk], stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE)
dtb = hardware / 'boot-components/stock.dtb'
dtbo = hardware / 'boot-images/dtbo.img'
dt_hashes = json.loads((work / 'reports/sheng-stock-preparation.json').read_text())['stock_dt']
assert digest(dtbo) == dt_hashes['dtbo.img']
assert digest(dtb) == dt_hashes['dtb/stock.dtb']
# avbtool resolves its recovery hash descriptor as recovery.img in this folder.
image = build / 'recovery.img'
run([sys.executable, rom / 'system/tools/mkbootimg/mkbootimg.py',
     '--header_version', config['header_version'], '--pagesize', config['page_size'],
     '--base', config['base'], '--kernel_offset', config['kernel_offset'],
     '--ramdisk_offset', config['ramdisk_offset'], '--second_offset', '0',
     '--tags_offset', config['tags_offset'], '--dtb_offset', config['dtb_offset'],
     '--os_version', config['recovery_os_version'], '--os_patch_level', config['recovery_os_patch_level'],
     '--kernel', kernel_gz, '--ramdisk', ramdisk, '--dtb', dtb,
     '--recovery_dtbo', dtbo, '--cmdline', config['cmdline'], '--output', image])
assert image.stat().st_size < config['partition_size'] - 128 * 1024
avbtool = rom / 'out/host/linux-x86/bin/avbtool'
run([avbtool, 'add_hash_footer', '--image', image,
     '--partition_name', 'recovery', '--partition_size', config['partition_size'],
     '--algorithm', 'SHA256_RSA4096', '--key', rom / 'external/avb/test/data/testkey_rsa4096.pem'])
run([avbtool, 'verify_image', '--image', image], stdout=subprocess.PIPE)
verified = build / 'verified'
header = run([sys.executable, rom / 'system/tools/mkbootimg/unpack_bootimg.py',
              '--boot_img', image, '--out', verified], capture_output=True, text=True).stdout
assert 'boot image header version: 2' in header
assert gzip.decompress((verified / 'kernel').read_bytes()) == kernel.read_bytes()
assert digest(verified / 'ramdisk') == digest(ramdisk)
assert run(['lz4', '-dc', verified / 'ramdisk'], capture_output=True).stdout == cpio_file.read_bytes()
assert digest(verified / 'dtb') == digest(dtb)
assert digest(verified / 'recovery_dtbo') == digest(dtbo)
target = destination / 'lineage-24.0-sheng-recovery-r2.img'
shutil.copyfile(image, target)
assert digest(target) == digest(image)
report = {'revision': 'r2', 'image': target.name, 'bytes': target.stat().st_size,
          'sha256': digest(target), 'hardware_boot_tested': False,
          'source_recovery_sha256': expected, 'kernel_release': release,
          'kernel_source': 'own supplied official firmware; source-built kernel NOT used',
          'kernel_sha256': digest(kernel), 'dtb_sha256': digest(dtb), 'dtbo_sha256': digest(dtbo),
          'stock_module_count': len(selected), 'stock_modules_sha256': module_hashes,
          'header': header, 'configuration': config, 'commands': commands,
          'tests': {'avb_hash_and_signature_verified': True,
                    'embedded_kernel_dtb_dtbo_readback_equal': True,
                    'module_load_entries_and_depmod_index_complete': True,
                    'kmod_all_load_entries_dry_run_passed': True,
                    'windows_export_sha256_equal': True},
          'boot_partition_dependency': False, 'vendor_boot_dependency': False,
          'init_boot_dependency': False}
(destination / 'recovery-build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(destination / 'SHA256SUMS').write_text(f"{report['sha256']}  {target.name}\n")
(work / 'reports/standalone-recovery-r2.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: report[key] for key in ('image', 'bytes', 'sha256', 'kernel_release', 'stock_module_count')}, indent=2))
