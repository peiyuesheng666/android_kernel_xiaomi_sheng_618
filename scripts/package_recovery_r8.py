#!/usr/bin/env python3
"""Carry proven r7 display startup into r8 with source kernel and board touch."""
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import tarfile

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
product = rom / 'out/target/product/sheng'
kernel_out = product / 'obj/KERNEL_OBJ'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', default='r8-source-touch')
parser.add_argument('--native-init', action='store_true')
parser.add_argument('--raw-kernel', action='store_true')
parser.add_argument('--safe-layout', action='store_true')
parser.add_argument('--trim-dtbo', action='store_true')
parser.add_argument('--ramdisk-compression', choices=('lz4', 'gzip', 'zstd'), default='lz4')
parser.add_argument('--touch-firmware-delay-ms', type=int, choices=(1000,))
arguments = parser.parse_args()
revision = arguments.revision
assert revision.replace('-', '').isalnum()
build = rom.parent / ('recovery-' + revision) / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
destination = work / 'artifacts' / ('recovery-sheng-lineage-24.0-' + revision)
configuration = work / 'device/xiaomi/sheng/recovery'
base = json.loads((work / 'reports/recovery-r7-qti-handoff.json').read_text())
config = json.loads((configuration / 'standalone.json').read_text())
if arguments.safe_layout:
    config.update(ramdisk_offset='0x04000000', dtb_offset='0x08000000', tags_offset='0x07f00000')
exported = json.loads((work / 'artifacts/lineage-24.0-20261105-UNOFFICIAL-sheng/build-result.json').read_text())
commands = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(arguments, **kwargs):
    arguments = list(map(str, arguments))
    commands.append(arguments)
    return subprocess.run(arguments, check=True, **kwargs)


assert shutil.disk_usage('/mnt/c').free > 20 * 1024**3
assert not destination.exists(), 'Preserve any existing r8 artifacts'
build.mkdir(parents=True)
base_image = work / 'artifacts/recovery-sheng-lineage-24.0-r7-qti-handoff' / base['image']
assert sha(base_image) == base['sha256']
parts = build / 'base-parts'
run([sys.executable, rom / 'system/tools/mkbootimg/unpack_bootimg.py', '--boot_img', base_image, '--out', parts], stdout=subprocess.DEVNULL)
root = build / 'root'
root.mkdir()
archive = run(['lz4', '-dc', parts / 'ramdisk'], capture_output=True).stdout
run(['cpio', '-idmu', '--no-absolute-filenames'], cwd=root, input=archive, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

# Check the kernel against the immutable boot image from our successful build.
source_boot = work / 'artifacts/lineage-24.0-20261105-UNOFFICIAL-sheng/boot.img'
expected_boot = next(item['sha256'] for item in exported['files'] if item['name'] == 'boot.img')
assert sha(source_boot) == expected_boot
boot_parts = build / 'source-boot'
run([sys.executable, rom / 'system/tools/mkbootimg/unpack_bootimg.py', '--boot_img', source_boot, '--out', boot_parts], stdout=subprocess.DEVNULL)
kernel = kernel_out / 'arch/arm64/boot/Image.gz'
raw_kernel = gzip.decompress(kernel.read_bytes())
assert raw_kernel == (kernel_out / 'arch/arm64/boot/Image').read_bytes()
exported_kernel = (boot_parts / 'kernel').read_bytes()
if exported_kernel.startswith(b'\x1f\x8b'):
    exported_kernel = gzip.decompress(exported_kernel)
assert exported_kernel.startswith(raw_kernel), 'Kernel differs from the exported source build'
assert exported_kernel[len(raw_kernel):] in (b'', (parts / 'dtb').read_bytes())
release = (kernel_out / 'include/config/kernel.release').read_text().strip()
assert release == exported['board_module_abi']['release'] == '5.15.220-gf9ca2b71f672'
assert b'Linux version ' + release.encode() in raw_kernel
assert 'CONFIG_MODVERSIONS=y' in (kernel_out / '.config').read_text().splitlines()
if arguments.raw_kernel:
    kernel = kernel_out / 'arch/arm64/boot/Image'
config['kernel_strategy'] = 'source-kernel-with-ABI-verified-board-modules'

# Keep exact board modules, replace only the two GKI modules with our build.
module_dirs = list((root / 'lib/modules').iterdir())
assert len(module_dirs) == 1 and module_dirs[0].is_dir()
old_release = module_dirs[0].name
modules = root / 'lib/modules' / release
module_dirs[0].rename(modules)
staging = product / 'obj/PACKAGING/kernel_modules_intermediates/lib/modules' / release
stock_inventory = json.loads((work / 'reports/stock-all-module-abi.json').read_text())['closure_inputs']
board_module_patches = []
if arguments.touch_firmware_delay_ms is not None:
    patch_spec = importlib.util.spec_from_file_location('touch_delay_patch', work / 'scripts/patch_recovery_touch_delay.py')
    patcher = importlib.util.module_from_spec(patch_spec)
    patch_spec.loader.exec_module(patcher)
    hz = int(next(line.split('=', 1)[1] for line in (kernel_out / '.config').read_text().splitlines()
                  if line.startswith('CONFIG_HZ=')))
    board_module_patches.append(patcher.patch_module(modules / 'nt36532_touch.ko', arguments.touch_firmware_delay_ms, hz))
source_module_paths = {}
for name in ('zram.ko', 'zsmalloc.ko'):
    candidates = [path for path in staging.rglob(name) if not path.is_relative_to(staging / 'extra/sheng')]
    assert len(candidates) == 1, (name, candidates)
    source_module_paths[name] = candidates[0]
    shutil.copyfile(candidates[0], modules / name)
spec = importlib.util.spec_from_file_location('sheng_abi', work / 'device/xiaomi/sheng/kernel/stock-modules/stage.py')
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)
core = {}
for line in (kernel_out / 'Module.symvers').read_text().splitlines():
    fields = line.split()
    if len(fields) >= 3 and fields[2] == 'vmlinux':
        core[fields[1]] = int(fields[0], 16)
exports = {symbol: (crc, 'vmlinux') for symbol, crc in core.items()}
module_objects = {path.name: abi.Module(path) for path in modules.glob('*.ko')}
module_hashes = {}
for name, module in module_objects.items():
    module_hashes[name] = hashlib.sha256(module.data).hexdigest()
    if name in source_module_paths:
        assert module.info['vermagic'].split()[0] == release
    elif name == 'nt36532_touch.ko' and board_module_patches:
        assert module_hashes[name] == board_module_patches[0]['patched_sha256']
    else:
        assert module_hashes[name] == stock_inventory[name]['sha256']
    assert 'modversions' in module.info['vermagic'].split()
    for symbol, crc in module.exports().items():
        assert symbol not in exports, f'Duplicate export: {name}:{symbol}'
        exports[symbol] = (crc, name)
imports_checked = 0
for name, module in module_objects.items():
    for symbol, expected in module.imports().items():
        assert symbol in exports, f'Missing provider: {name}:{symbol}'
        assert exports[symbol][0] == expected, f'CRC mismatch: {name}:{symbol}'
        imports_checked += 1
run(['depmod', '-b', root, release], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
order = root / 'diag/module-order'
order.write_text(order.read_text().replace('/lib/modules/' + old_release + '/', '/lib/modules/' + release + '/'))
for line in order.read_text().splitlines():
    path = line.split('\t', 1)[0]
    assert (root / path.lstrip('/')).is_file(), path
loads = (modules / 'modules.load.recovery').read_text().splitlines()
run(['modprobe', '--dry-run', '--all', '--verbose', '--dirname', root, '--set-version', release,
     *[name.removesuffix('.ko') for name in loads if name.strip()]], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# Place dependencies in the recovery namespace and models at their real paths.
touch = work / 'tools/sheng-touch-runtime'
stock = rom.parent / 'firmware-dump/partitions/odm'
touch_inputs = {
    'system/bin/touch_report_debug': ('bin/touch_report_debug', 0o755),
    'system/lib64/libtouchsensor.so': ('lib64/libtouchsensor.so', 0o644),
    'system/lib64/libtensorflowlite_touch_c.so': ('lib64/libtensorflowlite_touch_c.so', 0o644),
    'vendor/firmware/n81a_nova_thp_config.ini': ('firmware/n81a_nova_thp_config.ini', 0o644),
    'vendor/odm/firmware/film_model.tflite': ('firmware/film_model.tflite', 0o644),
    'vendor/odm/firmware/water_check.tflite': ('firmware/water_check.tflite', 0o644),
    'vendor/odm/firmware/glove_model.tflite': ('firmware/glove_model.tflite', 0o644),
}
touch_hashes = {}
for target_name, (source_name, mode) in touch_inputs.items():
    source = stock / source_name
    assert sha(source) == sha(touch / source.name), 'Live-tested touch input changed'
    target = root / target_name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(mode)
    touch_hashes[target_name] = sha(target)
assert (root / 'odm/firmware').is_symlink()
assert str((root / 'odm/firmware').readlink()) == '/vendor/odm/firmware'
shutil.copyfile(configuration / 'touch.sh', root / 'system/bin/sheng-recovery-touch')
(root / 'system/bin/sheng-recovery-touch').chmod(0o755)
qcom_rc = root / 'system/etc/init/init.recovery.qcom.rc'
if arguments.native_init:
    # Recovery's main script explicitly imports the root hardware file. Keep
    # one copy so directory scanning cannot register the same services twice.
    assert 'import /init.recovery.${ro.hardware}.rc' in (root / 'system/etc/init/hw/init.rc').read_text()
    if qcom_rc.exists():
        qcom_rc.unlink()
    qcom_rc = root / 'init.recovery.qcom.rc'
shutil.copyfile(configuration / 'init.recovery.sheng.rc', qcom_rc)
run([rom / 'out/host/linux-x86/bin/host_init_verifier', qcom_rc])
run(['bash', '-n', configuration / 'touch.sh'])
for path in root.rglob('*fstab*'):
    if path.is_file() and not path.is_symlink():
        text = path.read_text()
        path.write_text(text.replace('/dev/block/bootdevice/by-name/', '/dev/block/by-name/'))
fstab = root / 'system/etc/recovery.fstab'
assert '/dev/block/by-name/misc' in fstab.read_text()
assert '/dev/block/bootdevice/by-name/' not in fstab.read_text()
shutil.copyfile(product / 'recovery/root/sepolicy', root / 'sepolicy')
if arguments.native_init:
    (root / 'init').unlink()
    (root / 'init').symlink_to('/system/bin/init')
properties = root / 'prop.default'
overrides = {'ro.sheng.recovery.variant': revision}
if arguments.native_init:
    overrides['ro.sheng.recovery.diagnostic'] = 'native-init'
lines = [line for line in properties.read_text().splitlines() if line.split('=', 1)[0] not in overrides]
properties.write_text('\n'.join(lines) + '\n' + ''.join(key + '=' + value + '\n' for key, value in overrides.items()))
cmdline = base['cmdline'].replace('sheng_recovery_test=r7-qti-handoff', 'sheng_recovery_test=' + revision)
assert 'sheng_recovery_test=' + revision in cmdline

cpio = build / 'ramdisk.cpio'
with cpio.open('wb') as output:
    run([rom / 'out/host/linux-x86/bin/mkbootfs', '-d', product, root], stdout=output)
ramdisk = build / ('ramdisk.' + {'lz4': 'lz4', 'gzip': 'gz', 'zstd': 'zst'}[arguments.ramdisk_compression])
kernel_configuration = (kernel_out / '.config').read_text().splitlines()
assert 'CONFIG_RD_' + arguments.ramdisk_compression.upper() + '=y' in kernel_configuration
if arguments.ramdisk_compression == 'lz4':
    run(['lz4', '-l', '-12', '-f', cpio, ramdisk], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
elif arguments.ramdisk_compression == 'gzip':
    with ramdisk.open('wb') as output:
        run(['gzip', '-n', '-9', '-c', cpio], stdout=output)
else:
    run(['zstd', '-q', '-19', '-T0', '-f', cpio, '-o', ramdisk])
if arguments.safe_layout:
    assert int(config['kernel_offset'], 16) + len(raw_kernel) <= int(config['ramdisk_offset'], 16)
    assert int(config['ramdisk_offset'], 16) + ramdisk.stat().st_size <= int(config['tags_offset'], 16)
image = build / 'recovery.img'
dtbo = parts / 'recovery_dtbo'
dtbo_input = dtbo.read_bytes()
if arguments.trim_dtbo:
    magic, total, header, entry_size, count, entries_offset, _, _ = struct.unpack_from('>8I', dtbo_input)
    assert magic == 0xd7b7ab1e and header >= 32 and entry_size >= 32
    assert entries_offset + count * entry_size <= total <= len(dtbo_input)
    for index in range(count):
        size, offset = struct.unpack_from('>2I', dtbo_input, entries_offset + index * entry_size)
        assert offset + size <= total
        assert dtbo_input[offset:offset + 4] == b'\xd0\x0d\xfe\xed'
    dtbo = build / 'recovery-dtbo-payload.img'
    dtbo.write_bytes(dtbo_input[:total])
run([sys.executable, rom / 'system/tools/mkbootimg/mkbootimg.py', '--header_version', '2', '--pagesize', config['page_size'],
     '--base', config['base'], '--kernel_offset', config['kernel_offset'], '--ramdisk_offset', config['ramdisk_offset'],
     '--tags_offset', config['tags_offset'], '--dtb_offset', config['dtb_offset'], '--second_offset', '0',
     '--os_version', config['recovery_os_version'], '--os_patch_level', config['recovery_os_patch_level'],
     '--kernel', kernel, '--ramdisk', ramdisk, '--dtb', parts / 'dtb', '--recovery_dtbo', dtbo,
     '--cmdline', cmdline, '--output', image])
avbtool = rom / 'out/host/linux-x86/bin/avbtool'
run([avbtool, 'add_hash_footer', '--image', image, '--partition_name', 'recovery', '--partition_size', config['partition_size'],
     '--algorithm', 'SHA256_RSA4096', '--key', rom / 'external/avb/test/data/testkey_rsa4096.pem'])
run([avbtool, 'verify_image', '--image', image], stdout=subprocess.PIPE)
verified = build / 'verified'
run([sys.executable, rom / 'system/tools/mkbootimg/unpack_bootimg.py', '--boot_img', image, '--out', verified], stdout=subprocess.DEVNULL)
assert sha(verified / 'kernel') == sha(kernel)
assert sha(verified / 'ramdisk') == sha(ramdisk)
assert sha(verified / 'dtb') == sha(parts / 'dtb')
assert sha(verified / 'recovery_dtbo') == sha(dtbo)
assert (verified / 'recovery_dtbo').read_bytes() == dtbo_input[:dtbo.stat().st_size]
verified_root = build / 'verified-root'
verified_root.mkdir()
decompressor = {'lz4': 'lz4', 'gzip': 'gzip', 'zstd': 'zstd'}[arguments.ramdisk_compression]
raw = run([decompressor, '-dc', verified / 'ramdisk'], capture_output=True).stdout
run(['cpio', '-idmu', '--no-absolute-filenames'], cwd=verified_root, input=raw, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
for path, expected in touch_hashes.items():
    assert sha(verified_root / path) == expected
for relative in ('sepolicy', 'system/etc/recovery.fstab', str(qcom_rc.relative_to(root)), 'system/bin/sheng-recovery-touch', 'system/lib64/librecovery_ui.so', 'diag/module-order'):
    assert sha(verified_root / relative) == sha(root / relative)
if arguments.native_init:
    assert (verified_root / 'init').is_symlink()
    assert str((verified_root / 'init').readlink()) == '/system/bin/init'
else:
    assert sha(verified_root / 'init') == sha(root / 'init')
assert {path.name: sha(path) for path in (verified_root / 'lib/modules' / release).glob('*.ko')} == module_hashes
target = destination / ('lineage-24.0-sheng-recovery-' + revision + '.img')
destination.mkdir(parents=True)
shutil.copyfile(image, target)
assert sha(target) == sha(image)
report = {
    'revision': revision, 'image': target.name, 'bytes': target.stat().st_size, 'sha256': sha(target), 'work_dir': str(build),
    'base_r7_sha256': base['sha256'], 'kernel_release': release, 'kernel_sha256': sha(kernel),
    'kernel_source': 'Official LineageOS SM8550 source built in this project; matches exported boot image',
    'kernel_git_commit': run(['git', '-C', rom / 'kernel/xiaomi/sm8550', 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip(),
    'kernel_symvers_sha256': sha(kernel_out / 'Module.symvers'), 'dtb_and_dtbo_payload_unchanged_from_working_r7': True,
    'embedded_dtbo_partition_padding_removed': arguments.trim_dtbo, 'embedded_dtbo_bytes': dtbo.stat().st_size,
    'module_count': len(module_objects), 'source_modules': sorted(source_module_paths), 'modules_sha256': module_hashes,
    'module_imports_checked': imports_checked, 'module_abi_errors': [], 'module_vermagic_and_crc_modified': False,
    'board_module_patches': board_module_patches,
    'touch_inputs_sha256': touch_hashes, 'touch_live_test_user_confirmed': 'r7 RAM test: display normal and taps work',
    'misc_path': '/dev/block/by-name/misc', 'bootdevice_alias': '/dev/block/platform/soc/${ro.boot.bootdevice:-1d84000.ufshc}',
    'misc_alias_live_read_test_passed': True, 'sepolicy_sha256': sha(root / 'sepolicy'), 'cmdline': cmdline,
    'new_image_hardware_boot_tested': False, 'avb_verified': True, 'embedded_files_readback_verified': True, 'commands': commands,
    'native_android_init': arguments.native_init, 'serial_host_go_required': not arguments.native_init,
    'kernel_format': 'raw' if arguments.raw_kernel else 'gzip', 'boot_layout': config,
    'ramdisk_compression': arguments.ramdisk_compression,
    'hardware_init_rc': str(qcom_rc.relative_to(root)), 'hardware_init_rc_sha256': sha(qcom_rc),
    'touch_rotation': next((line.split()[-1] for line in qcom_rc.read_text().splitlines()
                            if line.strip().startswith('setprop ro.minui.default_touch_rotation ')), 'ROTATION_NONE'),
}
(destination / 'recovery-build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(work / 'reports' / ('recovery-' + revision + '.json')).write_text(json.dumps(report, indent=2) + '\n')
with tarfile.open(destination / 'recovery-source-configuration.tar.gz', 'w:gz') as output:
    for path in sorted(configuration.rglob('*')):
        if path.is_file():
            output.add(path, arcname=str(path.relative_to(work)))
    for name in ('scripts/package_recovery_r8.py', 'scripts/patch_recovery_touch_delay.py', 'scripts/build_recovery_policy.sh', 'device/xiaomi/sheng/rootdir/etc/fstab.qcom',
                 'device/xiaomi/sheng/sepolicy/vendor/init.te', 'device/xiaomi/sheng/sepolicy/vendor/file.te', 'device/xiaomi/sheng/sepolicy/vendor/genfs_contexts'):
        output.add(work / name, arcname=name)
(destination / 'SHA256SUMS').write_text(''.join(f'{sha(path)}  {path.name}\n' for path in sorted(destination.iterdir()) if path.is_file()))
print(json.dumps({key: report[key] for key in ('image', 'sha256', 'kernel_release', 'module_count', 'module_imports_checked', 'avb_verified')}, indent=2))
