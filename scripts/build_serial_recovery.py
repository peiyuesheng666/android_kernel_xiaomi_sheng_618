#!/usr/bin/env python3
"""Build r5: early serial diagnostics followed by independent recovery ADB."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
hardware = Path('/root/sheng-lineage/firmware-dump/hardware')
source_dir = work / 'artifacts/recovery-sheng-lineage-24.0-r2'
destination = work / 'artifacts/recovery-sheng-lineage-24.0-r5-adb'
build = Path('/root/sheng-lineage/recovery-r5') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
build.mkdir(parents=True)
destination.mkdir(parents=True, exist_ok=True)
commands = []


def run(args, **kwargs):
    args = list(map(str, args))
    commands.append(args)
    return subprocess.run(args, check=True, **kwargs)


def sha(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


receipt = json.loads((source_dir / 'recovery-build-result.json').read_text())
source_image = source_dir / receipt['image']
assert sha(source_image) == receipt['sha256']
parts = build / 'parts'
run([sys.executable, rom / 'system/tools/mkbootimg/unpack_bootimg.py',
     '--boot_img', source_image, '--out', parts], stdout=subprocess.DEVNULL)
root = build / 'root'
root.mkdir()
archive = run(['lz4', '-dc', parts / 'ramdisk'], capture_output=True).stdout
run(['cpio', '-idmu', '--no-absolute-filenames'], cwd=root, input=archive,
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
release = receipt['kernel_release']
module_dir = root / 'lib/modules' / release
blocklist = hardware / 'modules/vendor_boot/modules.blocklist'
shutil.copyfile(blocklist, module_dir / 'modules.blocklist')
blocked = {line.split()[1].replace('-', '_') for line in blocklist.read_text().splitlines()
           if line.startswith('blocklist ')}
dependencies = {}
for line in (module_dir / 'modules.dep').read_text().splitlines():
    key, values = line.split(':', 1)
    dependencies[Path(key).name] = [Path(value).name for value in values.split()]
soft_pre = {}
for line in (module_dir / 'modules.softdep').read_text().splitlines():
    fields = line.split()
    if fields[:1] != ['softdep']:
        continue
    values, mode = [], ''
    for value in fields[2:]:
        if value in ('pre:', 'post:'):
            mode = value
        elif mode == 'pre:':
            matches = [name for name in dependencies if name.removesuffix('.ko').replace('-', '_') == value.replace('-', '_')]
            if matches:
                values.append(matches[0])
    soft_pre[fields[1].replace('-', '_')] = values
order, visited, pending, skipped = [], set(), set(), []


def include(name, soft=False):
    if name in visited:
        return
    if name.removesuffix('.ko').replace('-', '_') in blocked:
        skipped.append(name)
        return
    assert name in dependencies, name
    if name in pending:
        assert soft, f'Hard dependency cycle: {name}'
        return
    pending.add(name)
    for item in dependencies[name]:
        include(item)
    for item in soft_pre.get(name.removesuffix('.ko').replace('-', '_'), []):
        include(item, soft=True)
    pending.remove(name)
    visited.add(name)
    order.append(name)


boot_roots = (work / 'device/xiaomi/sheng/configs/modules/modules.load.first_stage').read_text().splitlines()
usb_roots = ['eud.ko', 'phy-generic.ko', 'phy-msm-ssusb-qmp.ko', 'phy-msm-snps-eusb2.ko',
             'phy-msm-m31-eusb2.ko', 'dwc3-msm.ko', 'redriver.ko', 'ps5169.ko']
for name in boot_roots + usb_roots + (module_dir / 'modules.load.recovery').read_text().splitlines():
    if name in dependencies:
        include(name)
assert 'dwc3-msm.ko' in order
assert 'llcc_perfmon.ko' not in order

cmdline = receipt['configuration']['cmdline']
# mtdoops_init explicitly returns EINVAL without this required argument. Keep
# it visible in both the diagnostic loader and Android's cmdline option parser.
cmdline += ' mtdoops.mtddev=0 printk.devkmsg=on loglevel=7 log_buf_len=4M'
options = {}
for item in shlex.split(cmdline):
    if '=' not in item or '.' not in item.split('=', 1)[0]:
        continue
    key, value = item.split('=', 1)
    module, parameter = key.split('.', 1)
    options.setdefault(module.replace('-', '_'), []).append(f'{parameter}={value}')
diag = root / 'diag'
diag.mkdir()
lines = []
for name in order:
    assert re.fullmatch(r'[A-Za-z0-9_.-]+\.ko', name)
    parameters = ' '.join(options.get(name.removesuffix('.ko').replace('-', '_'), []))
    lines.append(f'/lib/modules/{release}/{name}\t{parameters}')
(diag / 'module-order').write_text('\n'.join(lines) + '\n')
tools = Path('/root/sheng-lineage/recovery-r3-tools')
tools.mkdir(exist_ok=True)
binary = tools / 'serial-init'
run(['aarch64-linux-gnu-gcc', '-O2', '-static', '-Wall', '-Wextra', '-Werror',
     '-o', binary, work / 'device/xiaomi/sheng/recovery/serial_init.c'])
run(['qemu-aarch64', binary, '--self-test'])
run([sys.executable, work / 'scripts/test_serial_transport.py'])
elf_headers = run(['aarch64-linux-gnu-readelf', '-l', binary], capture_output=True, text=True).stdout
assert 'INTERP' not in elf_headers
init = root / 'init'
assert init.is_symlink() and str(init.readlink()) == '/system/bin/init'
init.unlink()
shutil.copyfile(binary, init)
init.chmod(0o755)
properties = root / 'prop.default'
# Android 17 ProductNotDebuggableInUserdebug can generate debug=0 here.
# These explicit local-debug settings apply to this temporary image only.
overrides = {'ro.debuggable': '1', 'ro.adb.secure': '0', 'ro.secure': '0',
             'ro.sheng.recovery.diagnostic': 'serial-to-adb-r5'}
lines = [line for line in properties.read_text().splitlines()
         if line.split('=', 1)[0] not in overrides]
lines += ['# Temporary sheng diagnostic USB access, not production ROM defaults']
lines += [f'{key}={value}' for key, value in overrides.items()]
properties.write_text('\n'.join(lines) + '\n')
startup = root / 'system/etc/init/init.recovery.qcom.rc'
startup.write_text(startup.read_text() + '''
# Release the diagnostic-only ACM UDC after SELinux/init have taken over.
# Standard recovery init owns the normal g1 ADB/fastboot configuration.
on init
    write /config/usb_gadget/sheng_diag/UDC none

on boot
    setprop service.adb.root 1
    setprop sys.usb.config adb
''')
run([rom / 'out/host/linux-x86/bin/host_init_verifier', startup])
cpio = build / 'ramdisk.cpio'
with cpio.open('wb') as stream:
    run([rom / 'out/host/linux-x86/bin/mkbootfs', '-d', rom / 'out/target/product/sheng', root], stdout=stream)
ramdisk = build / 'ramdisk.lz4'
run(['lz4', '-l', '-12', '-f', cpio, ramdisk], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
config = receipt['configuration']
image = build / 'recovery.img'
run([sys.executable, rom / 'system/tools/mkbootimg/mkbootimg.py',
     '--header_version', '2', '--pagesize', config['page_size'], '--base', config['base'],
     '--kernel_offset', config['kernel_offset'], '--ramdisk_offset', config['ramdisk_offset'],
     '--tags_offset', config['tags_offset'], '--dtb_offset', config['dtb_offset'], '--second_offset', '0',
     '--os_version', config['recovery_os_version'], '--os_patch_level', config['recovery_os_patch_level'],
     '--kernel', parts / 'kernel', '--ramdisk', ramdisk, '--dtb', parts / 'dtb',
     '--recovery_dtbo', parts / 'recovery_dtbo', '--cmdline', cmdline, '--output', image])
avbtool = rom / 'out/host/linux-x86/bin/avbtool'
run([avbtool, 'add_hash_footer', '--image', image, '--partition_name', 'recovery',
     '--partition_size', config['partition_size'], '--algorithm', 'SHA256_RSA4096',
     '--key', rom / 'external/avb/test/data/testkey_rsa4096.pem'])
run([avbtool, 'verify_image', '--image', image], stdout=subprocess.PIPE)
verified = build / 'verified'
run([sys.executable, rom / 'system/tools/mkbootimg/unpack_bootimg.py',
     '--boot_img', image, '--out', verified], stdout=subprocess.DEVNULL)
for name in ('kernel', 'dtb', 'recovery_dtbo'):
    assert sha(parts / name) == sha(verified / name)
assert sha(verified / 'ramdisk') == sha(ramdisk)
target = destination / 'lineage-24.0-sheng-recovery-r5-adb.img'
shutil.copyfile(image, target)
assert sha(target) == sha(image)
report = {'revision': 'r5-adb', 'image': target.name, 'bytes': target.stat().st_size,
          'sha256': sha(target), 'source_r2_sha256': receipt['sha256'], 'work_dir': str(build),
          'static_preinit_sha256': sha(binary), 'module_bootstrap_count': len(order),
          'stock_blocklist_respected': sorted(set(skipped)), 'cmdline': cmdline,
          'kernel_dtb_dtbo_unchanged_from_r2': True, 'host_transport_test_passed': True,
          'avb_verified': True, 'hardware_boot_tested': False, 'usb_hardware_tested': False,
          'hold_before_android_init_until_host_go': True, 'commands': commands}
report['diagnostic_adb_properties'] = overrides
report['early_serial_to_normal_adb_handoff'] = True
(destination / 'serial-build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(destination / 'SHA256SUMS').write_text(f"{report['sha256']}  {target.name}\n")
(work / 'reports/recovery-r5.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: report[key] for key in ('image', 'sha256', 'bytes', 'module_bootstrap_count', 'stock_blocklist_respected')}))
