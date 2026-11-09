#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the original module layer plus a bounded, built-in rawdump logger."""
import argparse
import gzip
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
from sheng618_build_identity import configure as configure_identity, verify as verify_identity

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
stock = Path('/mnt/e/6/玩机资源/XiaomiPad6SPro12.4刷机资源/sheng_images_OS3.0.303.0.WNXCNXM_16.0/images/boot.img')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', default='disklog-r5')
parser.add_argument('--overlay', type=Path, default=K618 / 'boot-test/stage/overlay.cpio')
parser.add_argument('--test-timeout', type=int, choices=[180, 600],
                    help='Test only: return to bootloader at the selected uptime in seconds')
parser.add_argument('--pre-driver-hold-ms', type=int, default=0, choices=[0, 8000],
                    help='Test only: isolate faults occurring before board modules load')
parser.add_argument('--post-dispcc-hold-ms', type=int, default=0, choices=[0, 8000],
                    help='Test only: hold after display clock registration, before later drivers')
parser.add_argument('--before-display-hold-ms', type=int, default=0, choices=[0, 8000],
                    help='Test only: hold at display module entry after SoC driver loading')
parser.add_argument('--smmu-scan-watch-ms', type=int, default=0, choices=[0, 3000],
                    help='Read-only diagnostic watch duration; does not hold boot')
parser.add_argument('--kernel-compression', choices=['gzip', 'none'], default='gzip',
                    help='Use the sheng ABL gzip path verified by hardware-r58')
parser.add_argument('--legacy-module-reuse', action='store_true',
                    help='Recognize live replacements for stock 5.15 module duplicates')
parser.add_argument('--fscrypt-trace', action='store_true', help='Print only provisioning length/type/flags')
parser.add_argument('--legacy-fscrypt', action='store_true', help='Support old Android wrapped provisioning ABI')
parser.add_argument('--legacy-firmware-lsm', action='store_true', help='Match stock firmware SELinux load contract')
parser.add_argument('--replace-untested', action='store_true',
                    help='Replace only this unflashed candidate, preserving its directory')
parser.add_argument('--no-records', action='store_true',
                    help='Reuse installed source adaptations and omit progress/receipt files')
parser.add_argument('--release', action='store_true',
                    help='Compile out rawdump logger and package normal production boot arguments')
options = parser.parse_args()
if options.release:
    assert options.no_records, 'Release consumes the prepared, tested source tree'
    assert not any((options.test_timeout, options.pre_driver_hold_ms,
                    options.post_dispcc_hold_ms, options.before_display_hold_ms,
                    options.smmu_scan_watch_ms, options.fscrypt_trace)), 'Release cannot enable diagnostics'
assert sum(bool(x) for x in (options.pre_driver_hold_ms, options.post_dispcc_hold_ms,
                            options.before_display_hold_ms)) <= 1, 'Use a single stage hold'
if options.post_dispcc_hold_ms:
    assert b'TEST_ONLY post-clock hold begin' in options.overlay.read_bytes(), \
        'Overlay does not implement the selected stage hold'
if options.before_display_hold_ms:
    assert b'TEST_ONLY before-display hold begin' in options.overlay.read_bytes(), \
        'Overlay does not implement the selected display entry hold'
if options.smmu_scan_watch_ms:
    assert b'sheng_scan_watch_ms' in options.overlay.read_bytes(), \
        'Overlay does not implement the scan watch'
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
if not options.no_records and 'sheng_bootlog_fault_pause' in source.read_text():
    run([sys.executable, work / 'scripts/patch_sheng618_fault_capture.py'])
if not options.no_records and 'sheng_bootlog_test_mode' in source.read_text():
    run([sys.executable, work / 'scripts/patch_sheng618_test_reboot.py'])
if options.legacy_module_reuse and not options.no_records:
    run([sys.executable, work / 'scripts/patch_sheng618_module_reuse.py'])
if options.legacy_fscrypt and not options.no_records:
    run([sys.executable, work / 'scripts/patch_sheng618_fscrypt_legacy.py'])
elif options.fscrypt_trace and not options.no_records:
    run([sys.executable, work / 'scripts/patch_sheng618_fscrypt_trace.py'])
if options.legacy_firmware_lsm and not options.no_records:
    run([sys.executable, work / 'scripts/patch_sheng618_firmware_lsm.py'])
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
make = ['make', '-C', ACK, 'O=' + str(oi), 'ARCH=arm64', 'LLVM=1', 'LLVM_IAS=1',
        'PAHOLE=' + str(TOOLS / 'kernel-build-tools/linux_musl-x86/bin/pahole')]
log = LOGS / ('upstream-' + tag + '-image.log')
try:
    if options.no_records:
        verify_identity(oi, (K618 / 'out-gki/include/config/kernel.release').read_text().strip())
        assert 'CONFIG_SHENG_LEGACY_MODULE_REUSE' in (ACK / 'kernel/module/main.c').read_text()
        assert 'CONFIG_SHENG_LEGACY_FSCRYPT_PROVISIONING' in (ACK / 'fs/crypto/keyring.c').read_text()
        assert 'CONFIG_SHENG_LEGACY_FIRMWARE_LSM' in (ACK / 'security/selinux/hooks.c').read_text()
    else:
        configure_identity(ACK, oi, work)
    buffer_shift = int(re.search(rb'^CONFIG_LOG_BUF_SHIFT=(\d+)$',
                                (K618 / 'out-gki/.config').read_bytes(), re.M)[1]) if options.release else 22
    run([ACK / 'scripts/config', '--file', config,
         '--disable' if options.release else '--enable', 'SHENG_BOOTLOG',
         '--set-val', 'LOG_BUF_SHIFT', str(buffer_shift), '--set-str', 'INITRAMFS_SOURCE',
         options.overlay.resolve(), '--disable', 'INITRAMFS_FORCE'])
    run([ACK / 'scripts/config', '--file', config,
         '--enable' if options.legacy_module_reuse else '--disable', 'SHENG_LEGACY_MODULE_REUSE'])
    run([ACK / 'scripts/config', '--file', config,
         '--enable' if options.legacy_fscrypt else '--disable', 'SHENG_LEGACY_FSCRYPT_PROVISIONING'])
    run([ACK / 'scripts/config', '--file', config,
         '--enable' if options.legacy_firmware_lsm else '--disable', 'SHENG_LEGACY_FIRMWARE_LSM'])
    print('Building ' + ('release kernel' if options.release else 'built-in disk logger') + ': ' + str(log), flush=True)
    with log.open('w') as stream:
        run([*make, 'olddefconfig'], env=env, stdout=stream, stderr=subprocess.STDOUT)
        run([*make, '-j' + str(os.cpu_count()), 'Image'], env=env, stdout=stream, stderr=subprocess.STDOUT)
    if not options.no_records or options.release:
        (native / 'kernel.config').write_bytes(config.read_bytes())
    if options.release:
        assert '# CONFIG_SHENG_BOOTLOG is not set' in config.read_text()
        symbols = run([TOOLS / 'clang/host/linux-x86/clang-r584948c/bin/llvm-nm', oi / 'vmlinux'],
                      capture_output=True, text=True).stdout
        assert not re.search(r'\bsheng_bootlog_[A-Za-z0-9_]+$', symbols, re.M), 'Rawdump hooks remain'
    identity = verify_identity(oi, (K618 / 'out-gki/include/config/kernel.release').read_text().strip())
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
kernel_payload = image
if options.kernel_compression == 'gzip':
    kernel_payload = native / 'Image.gz'
    kernel_payload.write_bytes(gzip.compress(image.read_bytes(), compresslevel=9, mtime=0))
    assert gzip.decompress(kernel_payload.read_bytes()) == image.read_bytes()
args[args.index('--kernel') + 1] = str(kernel_payload)
cmdline = 'printk.devkmsg=on loglevel=7 sheng_bootlog.enable=1 sheng_test=' + tag
cmdline += ' sheng_bootlog.revision=' + tag
if options.release:
    cmdline = 'loglevel=4'
if options.pre_driver_hold_ms:
    cmdline += f' sheng_bootlog.pre_driver_hold_ms={options.pre_driver_hold_ms}'
if options.post_dispcc_hold_ms:
    cmdline += f' dispcc_kalama.sheng_postclock_hold_ms={options.post_dispcc_hold_ms}'
if options.before_display_hold_ms:
    cmdline += f' msm_drm.sheng_before_display_hold_ms={options.before_display_hold_ms}'
if options.smmu_scan_watch_ms:
    cmdline += f' arm_smmu.sheng_scan_watch_ms={options.smmu_scan_watch_ms}'
if options.test_timeout:
    cmdline += f' sheng_bootlog.test_timeout={options.test_timeout} panic=5'
args[args.index('--cmdline') + 1] = cmdline
packed = native / 'boot.img'
run([sys.executable, rom / 'system/tools/mkbootimg/mkbootimg.py', *args, '--output', packed])
avb = rom / 'out/host/linux-x86/bin/avbtool'
run([avb, 'add_hash_footer', '--image', packed, '--partition_name', 'boot',
     '--partition_size', stock.stat().st_size, '--algorithm', 'NONE'])
run([avb, 'verify_image', '--image', packed], capture_output=True)
verify = native / 'verified'
header = run([sys.executable, unpack, '--boot_img', packed, '--out', verify], capture_output=True, text=True).stdout
verified_kernel = (verify / 'kernel').read_bytes()
if options.kernel_compression == 'gzip':
    verified_kernel = gzip.decompress(verified_kernel)
assert verified_kernel == image.read_bytes() and (verify / 'ramdisk').read_bytes() == b''
assert cmdline in header and 'rdinit=' not in header
dest.mkdir(exist_ok=options.replace_untested)
shutil.copyfile(image, dest / 'Image')
shutil.copyfile(packed, dest / 'boot.img')
report = {'revision': tag, 'boot_sha256': sha(dest / 'boot.img'), 'image_sha256': sha(dest / 'Image'),
          'boot_bytes': packed.stat().st_size, 'image_bytes': image.stat().st_size,
          'logger_source_sha256': sha(source), 'kernel_exports_unchanged': len(actual),
          'build_identity': identity,
          'compiler_version_full': run([env['PATH'].split(':')[0] + '/clang', '--version'], capture_output=True, text=True).stdout,
          'original_android_init_preserved': True,
          'module_overlay': str(options.overlay.resolve()),
          'module_overlay_sha256': sha(options.overlay), 'usb_preinit_added': False,
          'kernel_log_buffer_bytes': 4 * 1024**2, 'writer_is_built_in': True,
          'periodic_log_identity': True,
          'snapshot_identity_trailer': True,
          'preserved_early_driver_trace_bytes': 128 * 1024,
          'destination': {'gpt_name': 'rawdump', 'required_partition_bytes': 300 * 1024**2,
                          'offset': 288 * 1024**2, 'span': 2 * 1024**2,
                          'slots': 2, 'slot_bytes': 1024**2},
          'interval_ms': 250, 'maximum_duration_ms': None,
          'fast_capture_duration_ms': (options.test_timeout + 20) * 1000 if options.test_timeout else 120000,
          'steady_interval_ms': 10000, 'late_exception_capture_retained': True,
          'normal_panic_capture_enabled': True,
          'test_timeout_seconds': options.test_timeout, 'crc32_and_footer': True,
          'legacy_live_module_reuse': options.legacy_module_reuse,
          'fscrypt_metadata_trace': 'sheng_fscrypt_abi: provisioning' in (ACK / 'fs/crypto/keyring.c').read_text(),
          'legacy_fscrypt_provisioning': options.legacy_fscrypt,
          'legacy_firmware_lsm': options.legacy_firmware_lsm,
          'does_not_require_sysfs_or_device_nodes': True,
          'requires_ufs_partition_registration': True, 'hardware_log_received': False,
          'cmdline': cmdline, 'build_log': str(log), 'maximum_retained_versions': 5}
if not options.release and 'sheng_bootlog_fault_pause' in source.read_text():
    report['fault_capture_receipt'] = 'kernel618-fault-capture-source.json'
    report['exception_pause_ms'] = 1500
    report['test_exception_pause_ms'] = 15000 if options.test_timeout else None
    report['exception_writer_runs_on_other_cpu'] = True
if options.release:
    for key in ('destination', 'interval_ms', 'maximum_duration_ms', 'fast_capture_duration_ms',
                'steady_interval_ms', 'preserved_early_driver_trace_bytes'):
        report.pop(key, None)
    report.update(build_type='release', rawdump_writes_enabled=False,
                  logger_source_sha256=None, writer_is_built_in=False,
                  periodic_log_identity=False, snapshot_identity_trailer=False,
                  late_exception_capture_retained=False, normal_panic_capture_enabled=False,
                  crc32_and_footer=False, requires_ufs_partition_registration=False,
                  fscrypt_metadata_trace=False, kernel_log_buffer_bytes=1 << buffer_shift,
                  kernel_config_sha256=sha(native / 'kernel.config'))
    shutil.copyfile(native / 'kernel.config', dest / 'kernel.config')
if not options.no_records or options.release:
    (dest / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(dest / 'SHA256SUMS').write_text(report['boot_sha256'] + '  boot.img\n' + report['image_sha256'] + '  Image\n')
if not options.no_records or options.release:
    (work / ('reports/kernel618-' + tag + '-boot.json')).write_text(json.dumps(report, indent=2) + '\n')
versions = sorted((p for p in (work / 'artifacts').glob('sheng-6.18-*') if p.is_dir()),
                  key=lambda p: p.stat().st_mtime, reverse=True)
for old in versions[5:]:
    assert old.parent.resolve() == (work / 'artifacts').resolve() and not old.is_symlink()
    shutil.rmtree(old)
if options.no_records:
    print('Built ' + tag + ': ' + report['boot_sha256'], flush=True)
else:
    print(json.dumps(report, indent=2), flush=True)
