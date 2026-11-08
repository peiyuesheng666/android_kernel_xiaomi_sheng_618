#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Repack the verified r8 kernel with upstream's existing cold-display option."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

project = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
root = Path('/root/sheng-618')
stock = Path('/mnt/e/6/玩机资源/XiaomiPad6SPro12.4刷机资源/sheng_images_OS3.0.303.0.WNXCNXM_16.0/images/boot.img')
tag = 'display-r9'
source = project / 'artifacts/sheng-6.18-display-r8/Image'
dest = project / ('artifacts/sheng-6.18-' + tag)
native = root / 'diagnostic' / tag
assert not dest.exists() and not (native / 'boot.img').exists(), 'Preserve tested revisions'

def sha(path):
    return hashlib.file_digest(Path(path).open('rb'), 'sha256').hexdigest()

def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)

assert sha(stock) == '4156a2369f78bc5df61b6a521b07a508dedf20d5e63c207d30986ae37df3eaea'
assert sha(source) == 'b5d2b44b566ac85bd704b50b5c63c2c13d2f07cca6e288d34d0e9b63950a4efb'
native.mkdir(parents=True, exist_ok=True)
unpack = rom / 'system/tools/mkbootimg/unpack_bootimg.py'
parts = native / 'stock-parts'
args = shlex.split(run([sys.executable, unpack, '--boot_img', stock, '--out', parts,
                       '--format=mkbootimg'], capture_output=True, text=True).stdout)
assert not (parts / 'ramdisk').read_bytes()
args[args.index('--kernel') + 1] = str(source)
cmdline = 'printk.devkmsg=on loglevel=7 sheng_bootlog.enable=1 sheng_test=' + tag + ' msm_drm.k618_cont_splash=0'
args[args.index('--cmdline') + 1] = cmdline
packed = native / 'boot.img'
run([sys.executable, rom / 'system/tools/mkbootimg/mkbootimg.py', *args, '--output', packed])
avb = rom / 'out/host/linux-x86/bin/avbtool'
run([avb, 'add_hash_footer', '--image', packed, '--partition_name', 'boot',
     '--partition_size', stock.stat().st_size, '--algorithm', 'NONE'])
run([avb, 'verify_image', '--image', packed], capture_output=True)
verify = native / 'verified'
header = run([sys.executable, unpack, '--boot_img', packed, '--out', verify],
             capture_output=True, text=True).stdout
assert sha(verify / 'kernel') == sha(source) and not (verify / 'ramdisk').read_bytes()
assert cmdline in header and 'rdinit=' not in header
dest.mkdir()
shutil.copyfile(source, dest / 'Image')
shutil.copyfile(packed, dest / 'boot.img')
report = dict(revision=tag, boot_sha256=sha(packed), image_sha256=sha(source),
              boot_bytes=packed.stat().st_size, image_bytes=source.stat().st_size,
              same_image_as_revision='display-r8', compiled=False,
              cmdline=cmdline, diagnostic_only=True,
              existing_upstream_module_option='msm_drm.k618_cont_splash=0',
              option_reference='upstream c3956156ce7c4193c451dfda531fad72d35bfebb kernel-6.18/k618_timg.sh and k618_tp_fix.py',
              interpretation='Map existing splash memory but omit old display-state handoff; diagnostic comparison, not a completed panel fix',
              kernel_readback_matches=True, avb_self_verification_passed=True,
              original_android_init_preserved=True, hardware_log_received=False,
              maximum_retained_versions=5)
(dest / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(dest / 'SHA256SUMS').write_text(report['boot_sha256'] + '  boot.img\n' + report['image_sha256'] + '  Image\n')
(project / ('reports/kernel618-' + tag + '-boot.json')).write_text(json.dumps(report, indent=2) + '\n')
versions = sorted((p for p in (project / 'artifacts').glob('sheng-6.18-*') if p.is_dir()),
                  key=lambda p: p.stat().st_mtime, reverse=True)
for old in versions[5:]:
    assert old.parent.resolve() == (project / 'artifacts').resolve() and not old.is_symlink()
    shutil.rmtree(old)
print(json.dumps(report, indent=2))
