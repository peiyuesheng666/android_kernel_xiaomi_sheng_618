#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Repack a verified kernel with gzip and an optional pre-driver timing hold."""
import argparse
import gzip
import hashlib
import re
import shlex
import shutil
import subprocess
import sys
from build_sheng618_upstream import PROJECT, ROOT

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', required=True)
parser.add_argument('--base', required=True)
parser.add_argument('--pre-driver-hold-ms', type=int, default=0, choices=[0, 8000],
                    help='Test only: enable the existing built-in eight-second hold')
args = parser.parse_args()
assert all(re.fullmatch(r'hardware-r[0-9]+', tag) for tag in (args.tag, args.base))
base = PROJECT / 'artifacts' / ('sheng-6.18-' + args.base)
dest = PROJECT / 'artifacts' / ('sheng-6.18-' + args.tag)
native = ROOT / 'diagnostic' / args.tag
assert base.is_dir() and not dest.exists() and not native.exists()
native.mkdir(parents=True)
image = (base / 'Image').read_bytes()
assert image[56:60] == b'ARM\x64'
if args.pre_driver_hold_ms:
    assert b'TEST_ONLY pre-driver hold begin' in image and b'pre_driver_hold_ms' in image, \
        'Selected kernel does not implement the requested hold'
compressed = gzip.compress(image, compresslevel=9, mtime=0)
assert gzip.decompress(compressed) == image
(native / 'Image.gz').write_bytes(compressed)
rom = ROOT.parent / 'sheng-lineage/lineage-24.0'
unpack = rom / 'system/tools/mkbootimg/unpack_bootimg.py'
result = subprocess.run([sys.executable, unpack, '--boot_img', base / 'boot.img',
    '--out', native / 'base-parts', '--format=mkbootimg'],
    check=True, capture_output=True, text=True)
options = shlex.split(result.stdout)
assert (native / 'base-parts/ramdisk').read_bytes() == b''
base_payload = (native / 'base-parts/kernel').read_bytes()
assert (gzip.decompress(base_payload) if base_payload.startswith(b'\x1f\x8b')
        else base_payload) == image
options[options.index('--kernel') + 1] = str(native / 'Image.gz')
cmdline_index = options.index('--cmdline') + 1
cmdline = options[cmdline_index]
assert args.base in cmdline
cmdline = re.sub(r'(?:^|\s)sheng_bootlog\.pre_driver_hold_ms=\S+', '', cmdline)
cmdline = cmdline.replace(args.base, args.tag)
if args.pre_driver_hold_ms:
    cmdline += f' sheng_bootlog.pre_driver_hold_ms={args.pre_driver_hold_ms}'
assert 'sheng_bootlog.test_timeout=' not in cmdline, 'Do not inherit timed reboots'
options[cmdline_index] = cmdline
boot = native / 'boot.img'
subprocess.run([sys.executable, rom / 'system/tools/mkbootimg/mkbootimg.py',
    *options, '--output', boot], check=True)
avb = rom / 'out/host/linux-x86/bin/avbtool'
subprocess.run([avb, 'add_hash_footer', '--image', boot, '--partition_name', 'boot',
    '--partition_size', str((base / 'boot.img').stat().st_size), '--algorithm', 'NONE'], check=True)
subprocess.run([avb, 'verify_image', '--image', boot], check=True, capture_output=True)
verified = subprocess.run([sys.executable, unpack, '--boot_img', boot,
    '--out', native / 'verified', '--format=mkbootimg'],
    check=True, capture_output=True, text=True)
verified_options = shlex.split(verified.stdout)
assert verified_options[verified_options.index('--cmdline') + 1] == cmdline
assert gzip.decompress((native / 'verified/kernel').read_bytes()) == image
assert (native / 'verified/ramdisk').read_bytes() == b''
dest.mkdir()
shutil.copyfile(base / 'Image', dest / 'Image')
shutil.copyfile(boot, dest / 'boot.img')
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
(dest / 'SHA256SUMS').write_text(digest(dest / 'boot.img') + '  boot.img\n' +
                              digest(dest / 'Image') + '  Image\n')
versions = sorted(PROJECT.joinpath('artifacts').glob('sheng-6.18-hardware-r*'),
                  key=lambda p: p.stat().st_mtime, reverse=True)
for old in versions[5:]:
    assert old.parent.resolve() == PROJECT.joinpath('artifacts').resolve()
    assert old.is_dir() and not old.is_symlink()
    shutil.rmtree(old)
print(f'{args.tag}: kernel payload {len(image)} -> {len(compressed)} bytes; '
      'decompressed kernel and embedded modules unchanged; AVB verified', flush=True)
print('Boot SHA256: ' + digest(dest / 'boot.img'), flush=True)
print(f'Pre-driver hold: {args.pre_driver_hold_ms} ms; cmdline readback verified', flush=True)
