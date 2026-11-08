#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Embed a USB ACM pre-init into the selected sheng kernel and stock boot v4.

Only creates local artifacts. Flashing is a separate, explicit operation.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from build_sheng618_upstream import ACK, BUILD, CLANG, K618, LOGS, ROOT, TOOLS, environment

WORK = Path(__file__).resolve().parents[1]
ROM = Path('/root/sheng-lineage/lineage-24.0')
STOCK = Path('/mnt/e/6/玩机资源/XiaomiPad6SPro12.4刷机资源/sheng_images_OS3.0.303.0.WNXCNXM_16.0/images/boot.img')
TAG = sys.argv[1] if len(sys.argv) > 1 else 'serial-r1'
BACKGROUND = '--background' in sys.argv[2:]
assert TAG.startswith('serial-r') and TAG.removeprefix('serial-r').isdigit()
DEST = WORK / 'artifacts' / ('sheng-6.18-' + TAG)
assert not DEST.exists(), 'Preserve existing revision; choose a new serial-rN'
BASE_SHA = '4156a2369f78bc5df61b6a521b07a508dedf20d5e63c207d30986ae37df3eaea'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


assert sha(STOCK) == BASE_SHA
stage = K618 / 'boot-test/stage/rd'
native = ROOT / 'diagnostic' / TAG
native.mkdir(parents=True)
binary = native / 'sheng_diag_init'
source = WORK / ('device/xiaomi/sheng/interfaces/kernel/6.18/serial_background.c' if BACKGROUND
                 else 'device/xiaomi/sheng/rootdir/recovery/serial_init.c')
run(['aarch64-linux-gnu-gcc', '-O2', '-static', '-Wall', '-Wextra', '-Werror',
     '-DSHENG_DIAG_INIT="/init"', '-DSHENG_DIAG_SERIAL="SHENG-618-' + TAG.upper() + '"',
     '-o', binary, source])
run(['qemu-aarch64', binary, '--self-test'])
run([sys.executable, WORK / 'scripts/test_serial_transport.py', '--binary', binary,
     '--report-name', 'kernel618-' + TAG + '-transport.json'])
assert 'INTERP' not in run(['aarch64-linux-gnu-readelf', '-l', binary], capture_output=True, text=True).stdout

# Load only the resource/USB closure before Android init. Stock module lists
# remain the upstream layer's responsibility after GO; no 5.15 module is used.
mods = stage / 'lib/modules'
deps = {}
for line in (mods / 'modules.dep').read_text().splitlines():
    key, values = line.split(':', 1)
    deps[Path(key).name] = [Path(value).name for value in values.split()]
blocked = {line.split()[1].replace('-', '_') for line in (mods / 'modules.blocklist').read_text().splitlines()
           if line.startswith('blocklist ')}
order, seen, active = [], set(), set()


def include(name):
    if name in seen:
        return
    assert name in deps, name
    assert name not in active, 'Hard dependency cycle: ' + name
    assert name.removesuffix('.ko').replace('-', '_') not in blocked, name
    active.add(name)
    for dependency in deps[name]:
        include(dependency)
    active.remove(name)
    seen.add(name)
    order.append(name)


roots = ['qcom_wdt_core.ko', 'clk-rpmh.ko', 'gcc-kalama.ko', 'pinctrl-kalama.ko',
         'spmi-pmic-arb.ko', 'qcom-spmi-pmic.ko', 'rpmh-regulator.ko', 'qnoc-kalama.ko',
         'phy-generic.ko', 'phy-msm-ssusb-qmp.ko', 'phy-msm-snps-eusb2.ko',
         'phy-msm-m31-eusb2.ko', 'repeater-qti-pmic-eusb2.ko', 'dwc3-msm.ko']
for name in ([] if BACKGROUND else roots):
    if name in deps:
        include(name)
assert BACKGROUND or 'dwc3-msm.ko' in order
assert 'k618_load.ko' not in order

# Append an independent small cpio to the verified original overlay. The
# integration unpacks its built-in archive last, after vendor_boot/init_boot.
extra = native / 'root'
(extra / 'diag').mkdir(parents=True)
shutil.copyfile(binary, extra / 'sheng_diag_init')
(extra / 'sheng_diag_init').chmod(0o755)
(extra / 'diag/module-order').write_text(''.join('/lib/modules/' + name + '\t\n' for name in order))
small = run([ROM / 'out/host/linux-x86/bin/mkbootfs', extra], capture_output=True).stdout
cpio = native / 'initramfs.cpio'
base_cpio = K618 / 'boot-test/stage/overlay.cpio'
cpio.write_bytes(base_cpio.read_bytes() + small)
oi = K618 / 'out-gki-ir'
config = oi / '.config'
saved_config = config.read_bytes()
env = environment(os.cpu_count())
env.update(KBUILD_BUILD_HOST='build-host', KBUILD_BUILD_USER='build-user', KBUILD_BUILD_VERSION='1')
make = ['make', '-C', ACK, 'O=' + str(oi), 'ARCH=arm64', 'LLVM=1', 'LLVM_IAS=1',
        'PAHOLE=' + str(TOOLS / 'kernel-build-tools/linux_musl-x86/bin/pahole')]
log = LOGS / ('upstream-' + TAG + '-image.log')
try:
    run([ACK / 'scripts/config', '--file', config, '--set-str', 'INITRAMFS_SOURCE', cpio,
         '--disable', 'INITRAMFS_FORCE'])
    print('Rebuilding embedded diagnostic Image; log: ' + str(log), flush=True)
    with log.open('w') as stream:
        run([*make, 'olddefconfig'], env=env, stdout=stream, stderr=subprocess.STDOUT)
        run([*make, '-j' + str(os.cpu_count()), 'Image'], env=env, stdout=stream, stderr=subprocess.STDOUT)
    baseline_exports = sorted(line for line in (K618 / 'out-gki/Module.symvers').read_text().splitlines()
                              if line.split('\t')[2] == 'vmlinux')
    assert baseline_exports == sorted((oi / 'vmlinux.symvers').read_text().splitlines())
    assert 'CONFIG_INITRAMFS_FORCE=y' not in config.read_text()
finally:
    config.write_bytes(saved_config)

image = oi / 'arch/arm64/boot/Image'
assert image.read_bytes()[56:60] == b'ARM\x64'
parts = native / 'stock-parts'
unpack = ROM / 'system/tools/mkbootimg/unpack_bootimg.py'
mkbootimg = ROM / 'system/tools/mkbootimg/mkbootimg.py'
args = shlex.split(run([sys.executable, unpack, '--boot_img', STOCK, '--out', parts,
                       '--format=mkbootimg'], capture_output=True, text=True).stdout)
assert args[args.index('--header_version') + 1] == '4'
assert (parts / 'ramdisk').stat().st_size == 0
args[args.index('--kernel') + 1] = str(image)
cmdline = 'rdinit=/sheng_diag_init printk.devkmsg=on loglevel=8 log_buf_len=8M ignore_loglevel '
if not BACKGROUND:
    cmdline += 'initcall_debug panic=0 '
cmdline += 'sheng_diag=' + TAG
args[args.index('--cmdline') + 1] = cmdline
packed = native / 'boot.img'
run([sys.executable, mkbootimg, *args, '--output', packed])
# Use an unsigned AVB hash footer for this explicitly unlocked-device test.
# The stock signature cannot authenticate a replaced kernel.
avb = ROM / 'out/host/linux-x86/bin/avbtool'
run([avb, 'add_hash_footer', '--image', packed, '--partition_name', 'boot',
     '--partition_size', STOCK.stat().st_size, '--algorithm', 'NONE'])
run([avb, 'verify_image', '--image', packed], capture_output=True)
verify = native / 'verified'
header = run([sys.executable, unpack, '--boot_img', packed, '--out', verify], capture_output=True, text=True).stdout
assert sha(verify / 'kernel') == sha(image)
assert (verify / 'ramdisk').read_bytes() == (parts / 'ramdisk').read_bytes()
assert cmdline in header
DEST.mkdir()
shutil.copyfile(packed, DEST / 'boot.img')
shutil.copyfile(image, DEST / 'Image')
report = {'revision': TAG, 'stock_boot_sha256': BASE_SHA,
          'original_test_image_sha256': '32afc9fa288989a949e8d5c6e83c159110d9ea62e60bd016efde7de7e7c58b70',
          'boot': str(DEST / 'boot.img'), 'boot_sha256': sha(DEST / 'boot.img'),
          'boot_bytes': packed.stat().st_size, 'image_sha256': sha(image),
          'static_preinit_sha256': sha(binary), 'usb_preinit_module_order': order,
          'module_layer_sha256': sha(base_cpio), 'diagnostic_cpio_sha256': sha(cpio),
          'cmdline': cmdline, 'kernel_exports_unchanged': len(baseline_exports),
          'stock_header_v4_retained': True, 'stock_boot_ramdisk_unchanged': True,
          'avb_self_verification_passed': True, 'avb_algorithm': 'NONE',
          'transport_qemu_test_passed': True, 'hardware_serial_verified': False,
          'background_capture': BACKGROUND, 'holds_android_init': not BACKGROUND,
          'build_log': str(log), 'maximum_retained_versions': 5}
(DEST / 'SHA256SUMS').write_text(report['boot_sha256'] + '  boot.img\n' + report['image_sha256'] + '  Image\n')
(WORK / ('reports/kernel618-' + TAG + '-boot.json')).write_text(json.dumps(report, indent=2) + '\n')
(DEST / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
# Retention applies only to this task's generated boot/Image release folders.
versions = sorted([p for p in (WORK / 'artifacts').glob('sheng-6.18-*') if p.is_dir()],
                  key=lambda p: p.stat().st_mtime, reverse=True)
for old in versions[5:]:
    assert old.parent.resolve() == (WORK / 'artifacts').resolve()
    assert not old.is_symlink()
    shutil.rmtree(old)
print(json.dumps(report, indent=2), flush=True)
