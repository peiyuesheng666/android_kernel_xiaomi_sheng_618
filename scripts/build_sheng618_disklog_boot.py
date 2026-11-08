#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the original module layer plus a bounded, built-in rawdump logger."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from build_sheng618_upstream import ACK, K618, LOGS, ROOT, TOOLS, environment

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
stock = Path('/mnt/e/6/玩机资源/XiaomiPad6SPro12.4刷机资源/sheng_images_OS3.0.303.0.WNXCNXM_16.0/images/boot.img')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', default='disklog-r5')
parser.add_argument('--overlay', type=Path, default=K618 / 'boot-test/stage/overlay.cpio')
parser.add_argument('--test-timeout', type=int, choices=[180],
                    help='Test only: return to bootloader at uptime 180 seconds')
parser.add_argument('--legacy-module-reuse', action='store_true',
                    help='Recognize live replacements for stock 5.15 module duplicates')
parser.add_argument('--fscrypt-trace', action='store_true', help='Print only provisioning length/type/flags')
parser.add_argument('--replace-untested', action='store_true',
                    help='Replace only this unflashed candidate, preserving its directory')
options = parser.parse_args()
tag = options.tag
assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}', tag), 'Invalid artifact label'
assert options.overlay.is_file()
native = ROOT / 'diagnostic' / tag
dest = work / 'artifacts' / ('sheng-6.18-' + tag)
if dest.exists():
    assert options.replace_untested, 'Preserve tested revisions'
    assert not (work / ('reports/device/kernel618-' + tag) / 'flash.txt').exists()
    assert not (work / ('reports/kernel618-' + tag + '-hardware.json')).exists()
    previous = json.loads((dest / 'build-result.json').read_text())
    assert previous['revision'] == tag and not previous['hardware_log_received']
native.mkdir(parents=True, exist_ok=True)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


assert sha(stock) == '4156a2369f78bc5df61b6a521b07a508dedf20d5e63c207d30986ae37df3eaea'
misc = ACK / 'drivers/misc'
source = work / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng_bootlog.c'
if 'sheng_bootlog_fault_pause' in source.read_text():
    run([sys.executable, work / 'scripts/patch_sheng618_fault_capture.py'])
if 'sheng_bootlog_test_mode' in source.read_text():
    run([sys.executable, work / 'scripts/patch_sheng618_test_reboot.py'])
if options.legacy_module_reuse:
    run([sys.executable, work / 'scripts/patch_sheng618_module_reuse.py'])
if options.fscrypt_trace:
    run([sys.executable, work / 'scripts/patch_sheng618_fscrypt_trace.py'])
shutil.copyfile(source, misc / 'sheng_bootlog.c')
makefile = misc / 'Makefile'
line = 'obj-$(CONFIG_SHENG_BOOTLOG) += sheng_bootlog.o\n'
if line not in makefile.read_text():
    with makefile.open('a') as stream:
        stream.write('\n' + line)
kconfig = misc / 'Kconfig'
if 'config SHENG_BOOTLOG\n' not in kconfig.read_text():
    with kconfig.open('a') as stream:
        stream.write('\nconfig SHENG_BOOTLOG\n\tbool "Bounded sheng rawdump boot logger"\n'
                     '\tdepends on BLOCK && PRINTK\n\tselect CRC32\n')
oi = K618 / 'out-gki-ir'
config = oi / '.config'
saved = config.read_bytes()
env = environment(os.cpu_count())
env.update(KBUILD_BUILD_HOST='build-host', KBUILD_BUILD_USER='build-user', KBUILD_BUILD_VERSION='1')
make = ['make', '-C', ACK, 'O=' + str(oi), 'ARCH=arm64', 'LLVM=1', 'LLVM_IAS=1',
        'PAHOLE=' + str(TOOLS / 'kernel-build-tools/linux_musl-x86/bin/pahole')]
log = LOGS / ('upstream-' + tag + '-image.log')
try:
    run([ACK / 'scripts/config', '--file', config, '--enable', 'SHENG_BOOTLOG',
         '--set-val', 'LOG_BUF_SHIFT', '22', '--set-str', 'INITRAMFS_SOURCE',
         options.overlay.resolve(), '--disable', 'INITRAMFS_FORCE'])
    run([ACK / 'scripts/config', '--file', config,
         '--enable' if options.legacy_module_reuse else '--disable', 'SHENG_LEGACY_MODULE_REUSE'])
    print('Building built-in disk logger: ' + str(log), flush=True)
    with log.open('w') as stream:
        run([*make, 'olddefconfig'], env=env, stdout=stream, stderr=subprocess.STDOUT)
        run([*make, '-j' + str(os.cpu_count()), 'Image'], env=env, stdout=stream, stderr=subprocess.STDOUT)
    (native / 'kernel.config').write_bytes(config.read_bytes())
    expected = sorted(line for line in (K618 / 'out-gki/Module.symvers').read_text().splitlines()
                      if line.split('\t')[2] == 'vmlinux')
    actual = sorted((oi / 'vmlinux.symvers').read_text().splitlines())
    assert expected == actual, 'Kernel module ABI changed'
finally:
    config.write_bytes(saved)
image = oi / 'arch/arm64/boot/Image'
assert image.read_bytes()[56:60] == b'ARM\x64'
unpack = rom / 'system/tools/mkbootimg/unpack_bootimg.py'
parts = native / 'stock-parts'
args = shlex.split(run([sys.executable, unpack, '--boot_img', stock, '--out', parts,
                       '--format=mkbootimg'], capture_output=True, text=True).stdout)
assert (parts / 'ramdisk').read_bytes() == b''
args[args.index('--kernel') + 1] = str(image)
cmdline = 'printk.devkmsg=on loglevel=7 sheng_bootlog.enable=1 sheng_test=' + tag
if options.test_timeout:
    cmdline += ' sheng_bootlog.test_timeout=180 panic=5'
args[args.index('--cmdline') + 1] = cmdline
packed = native / 'boot.img'
run([sys.executable, rom / 'system/tools/mkbootimg/mkbootimg.py', *args, '--output', packed])
avb = rom / 'out/host/linux-x86/bin/avbtool'
run([avb, 'add_hash_footer', '--image', packed, '--partition_name', 'boot',
     '--partition_size', stock.stat().st_size, '--algorithm', 'NONE'])
run([avb, 'verify_image', '--image', packed], capture_output=True)
verify = native / 'verified'
header = run([sys.executable, unpack, '--boot_img', packed, '--out', verify], capture_output=True, text=True).stdout
assert sha(verify / 'kernel') == sha(image) and (verify / 'ramdisk').read_bytes() == b''
assert cmdline in header and 'rdinit=' not in header
dest.mkdir(exist_ok=options.replace_untested)
shutil.copyfile(image, dest / 'Image')
shutil.copyfile(packed, dest / 'boot.img')
report = {'revision': tag, 'boot_sha256': sha(dest / 'boot.img'), 'image_sha256': sha(dest / 'Image'),
          'boot_bytes': packed.stat().st_size, 'image_bytes': image.stat().st_size,
          'logger_source_sha256': sha(source), 'kernel_exports_unchanged': len(actual),
          'original_android_init_preserved': True,
          'module_overlay': str(options.overlay.resolve()),
          'module_overlay_sha256': sha(options.overlay), 'usb_preinit_added': False,
          'kernel_log_buffer_bytes': 4 * 1024**2, 'writer_is_built_in': True,
          'destination': {'gpt_name': 'rawdump', 'required_partition_bytes': 300 * 1024**2,
                          'offset': 288 * 1024**2, 'span': 2 * 1024**2,
                          'slots': 2, 'slot_bytes': 1024**2},
          'interval_ms': 250, 'maximum_duration_ms': 200000 if options.test_timeout else 120000,
          'test_timeout_seconds': options.test_timeout, 'crc32_and_footer': True,
          'legacy_live_module_reuse': options.legacy_module_reuse,
          'fscrypt_metadata_trace': options.fscrypt_trace,
          'does_not_require_sysfs_or_device_nodes': True,
          'requires_ufs_partition_registration': True, 'hardware_log_received': False,
          'cmdline': cmdline, 'build_log': str(log), 'maximum_retained_versions': 5}
if 'sheng_bootlog_fault_pause' in source.read_text():
    report['fault_capture_receipt'] = 'kernel618-fault-capture-source.json'
    report['exception_pause_ms'] = 1500
    report['test_exception_pause_ms'] = 15000 if options.test_timeout else None
    report['exception_writer_runs_on_other_cpu'] = True
(dest / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(dest / 'SHA256SUMS').write_text(report['boot_sha256'] + '  boot.img\n' + report['image_sha256'] + '  Image\n')
(work / ('reports/kernel618-' + tag + '-boot.json')).write_text(json.dumps(report, indent=2) + '\n')
versions = sorted((p for p in (work / 'artifacts').glob('sheng-6.18-*') if p.is_dir()),
                  key=lambda p: p.stat().st_mtime, reverse=True)
for old in versions[5:]:
    assert old.parent.resolve() == (work / 'artifacts').resolve() and not old.is_symlink()
    shutil.rmtree(old)
print(json.dumps(report, indent=2), flush=True)
