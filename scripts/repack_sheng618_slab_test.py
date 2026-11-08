#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reuse r10 Image and enable allocation provenance for the corrupted slab pool."""
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
tag = 'slab-r11'
source = project / 'artifacts/sheng-6.18-fault-r10/Image'
dest = project / ('artifacts/sheng-6.18-' + tag)
native = root / 'diagnostic' / tag
assert not dest.exists() and not (native / 'boot.img').exists(), 'Preserve tested revisions'

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)

assert sha(stock) == '4156a2369f78bc5df61b6a521b07a508dedf20d5e63c207d30986ae37df3eaea'
assert sha(source) == '99d34cdb44cf1174c23451aad863adbc459d728268c509ca4905c632285e8f6a'
config = (root / 'diagnostic/fault-r10/kernel.config').read_text()
assert 'CONFIG_SLUB_DEBUG=y\n' in config and 'CONFIG_STACKDEPOT=y\n' in config
native.mkdir(parents=True, exist_ok=True)
unpack = rom / 'system/tools/mkbootimg/unpack_bootimg.py'
parts = native / 'stock-parts'
args = shlex.split(run([sys.executable, unpack, '--boot_img', stock, '--out', parts,
                       '--format=mkbootimg'], capture_output=True, text=True).stdout)
assert not (parts / 'ramdisk').read_bytes()
args[args.index('--kernel') + 1] = str(source)
# The stock vendor cmdline disables the depot. This later bool assignment is
# required for SLAB_STORE_USER call stacks; verify the override in QEMU too.
cmdline = ('printk.devkmsg=on loglevel=7 sheng_bootlog.enable=1 sheng_test=' + tag +
           ' stack_depot_disable=off slab_debug=U,kmalloc-2k')
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
              same_image_as_revision='fault-r10', compiled=False,
              cmdline=cmdline, diagnostic_only=True,
              slab_scope='kmalloc-2k only; U enables allocation/free provenance',
              evidence='r10 devices kset list BUG: corrupted prev in kmalloc-2k at offset 480',
              references=['ACK ff4a6c3bb0f471a9dd186293a47b62c83829b97d mm/slub.c setup_slub_debug, kmem_obj_info',
                          'Same ACK lib/stackdepot.c disable_stack_depot and mm/slab_common.c kmem_dump_obj'],
              kernel_readback_matches=True, avb_self_verification_passed=True,
              original_android_init_preserved=True, hardware_log_received=False,
              limitation='Changes slab placement/timing; allocation provenance is not by itself proof of the corrupting writer',
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
