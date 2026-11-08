#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Control boot: stock v4 container with only the first-test kernel replaced."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
stock = Path('/mnt/e/6/玩机资源/XiaomiPad6SPro12.4刷机资源/sheng_images_OS3.0.303.0.WNXCNXM_16.0/images/boot.img')
image = work / 'artifacts/sheng-6.18-first-boot/Image'
tag = 'baseline-r2'
native = Path('/root/sheng-618/diagnostic') / tag
dest = work / 'artifacts' / ('sheng-6.18-' + tag)
assert not dest.exists(), 'Do not overwrite a tested release'
native.mkdir(parents=True, exist_ok=True)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(args):
    return subprocess.run(list(map(str, args)), check=True, capture_output=True, text=True).stdout


assert sha(stock) == '4156a2369f78bc5df61b6a521b07a508dedf20d5e63c207d30986ae37df3eaea'
assert sha(image) == '32afc9fa288989a949e8d5c6e83c159110d9ea62e60bd016efde7de7e7c58b70'
assert image.read_bytes()[56:60] == b'ARM\x64'
unpack = rom / 'system/tools/mkbootimg/unpack_bootimg.py'
mkboot = rom / 'system/tools/mkbootimg/mkbootimg.py'
avb = rom / 'out/host/linux-x86/bin/avbtool'
parts = native / 'stock-parts'
args = shlex.split(run([sys.executable, unpack, '--boot_img', stock, '--out', parts, '--format=mkbootimg']))
original_args = args.copy()
args[args.index('--kernel') + 1] = str(image)
assert args[args.index('--cmdline') + 1] == ''
assert args[args.index('--header_version') + 1] == '4'
packed = native / 'boot.img'
run([sys.executable, mkboot, *args, '--output', packed])
run([avb, 'add_hash_footer', '--image', packed, '--partition_name', 'boot',
     '--partition_size', stock.stat().st_size, '--algorithm', 'NONE'])
run([avb, 'verify_image', '--image', packed])
verified = native / 'verified'
verified_args = shlex.split(run([sys.executable, unpack, '--boot_img', packed, '--out', verified, '--format=mkbootimg']))
for index, item in enumerate(original_args):
    if item in ('--kernel', '--ramdisk'):
        continue
    if index and original_args[index - 1] in ('--kernel', '--ramdisk'):
        continue
    assert item == verified_args[index], (item, verified_args[index])
assert (verified / 'ramdisk').read_bytes() == (parts / 'ramdisk').read_bytes() == b''
assert sha(verified / 'kernel') == sha(image)
dest.mkdir()
shutil.copyfile(packed, dest / 'boot.img')
report = {'revision': tag, 'boot_sha256': sha(dest / 'boot.img'), 'boot_bytes': packed.stat().st_size,
          'kernel_sha256': sha(image), 'official_boot_sha256': sha(stock),
          'original_header_arguments_preserved': True, 'original_empty_ramdisk_preserved': True,
          'diagnostic_preinit_added': False, 'additional_cmdline': '',
          'avb_self_verification_passed': True, 'avb_algorithm': 'NONE',
          'boot_test_result': 'pending', 'maximum_retained_versions': 5}
(dest / 'SHA256SUMS').write_text(report['boot_sha256'] + '  boot.img\n')
(dest / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(work / 'reports/kernel618-baseline-r2-boot.json').write_text(json.dumps(report, indent=2) + '\n')
versions = sorted((p for p in (work / 'artifacts').glob('sheng-6.18-*') if p.is_dir()),
                  key=lambda p: p.stat().st_mtime, reverse=True)
for old in versions[5:]:
    assert old.parent.resolve() == (work / 'artifacts').resolve() and not old.is_symlink()
    shutil.rmtree(old)
print(json.dumps(report, indent=2))
