#!/usr/bin/env python3
"""Keep the working r5 startup/kernel while changing only compiled QTI UI files."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--revision', default='r6-qti')
parser.add_argument('--diagnostic-init', type=Path)
args = parser.parse_args()
assert args.revision.replace('-', '').isalnum()
work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
base = json.loads((work / 'reports/recovery-r5.json').read_text())
qti = json.loads((work / 'reports/qti-candidate.json').read_text())
config = json.loads((work / 'device/xiaomi/sheng/recovery/standalone.json').read_text())
build = Path('/root/sheng-lineage') / ('recovery-' + args.revision) / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
destination = work / 'artifacts' / ('recovery-sheng-lineage-24.0-' + args.revision)
build.mkdir(parents=True)
destination.mkdir(parents=True, exist_ok=True)


def sha(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


commands = []


def run(args, **kwargs):
    args = list(map(str, args))
    commands.append(args)
    return subprocess.run(args, check=True, **kwargs)


image = work / 'artifacts/recovery-sheng-lineage-24.0-r5-adb' / base['image']
assert sha(image) == base['sha256']
parts = build / 'parts'
run([sys.executable, rom / 'system/tools/mkbootimg/unpack_bootimg.py',
     '--boot_img', image, '--out', parts], stdout=subprocess.DEVNULL)
root = build / 'root'
root.mkdir()
raw = run(['lz4', '-dc', parts / 'ramdisk'], capture_output=True).stdout
run(['cpio', '-idmu', '--no-absolute-filenames'], cwd=root, input=raw,
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
source_root = rom / 'out/target/product/sheng/recovery/root'
changed = {}
for relative in ('system/bin/recovery', 'system/lib64/librecovery_ui.so',
                 'system/lib64/librecovery_ui_ext.so'):
    source, target = source_root / relative, root / relative
    before = sha(target)
    shutil.copyfile(source, target)
    changed[relative] = {'before': before, 'after': sha(target)}
assert changed['system/lib64/librecovery_ui.so']['after'] == qti['sha256']
assert changed['system/lib64/librecovery_ui.so']['before'] == qti['original_sha256']
with (root / 'prop.default').open('a') as stream:
    stream.write('\nro.sheng.recovery.variant=' + args.revision + '\n')
if args.diagnostic_init:
    shutil.copyfile(args.diagnostic_init, root / 'init')
    (root / 'init').chmod(0o755)
cmdline = base['cmdline'] + ' sheng_recovery_test=' + args.revision
cpio = build / 'ramdisk.cpio'
with cpio.open('wb') as stream:
    run([rom / 'out/host/linux-x86/bin/mkbootfs', '-d', rom / 'out/target/product/sheng', root], stdout=stream)
ramdisk = build / 'ramdisk.lz4'
run(['lz4', '-l', '-12', '-f', cpio, ramdisk], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
output = build / 'recovery.img'
run([sys.executable, rom / 'system/tools/mkbootimg/mkbootimg.py',
     '--header_version', '2', '--pagesize', config['page_size'], '--base', config['base'],
     '--kernel_offset', config['kernel_offset'], '--ramdisk_offset', config['ramdisk_offset'],
     '--tags_offset', config['tags_offset'], '--dtb_offset', config['dtb_offset'], '--second_offset', '0',
     '--os_version', config['recovery_os_version'], '--os_patch_level', config['recovery_os_patch_level'],
     '--kernel', parts / 'kernel', '--ramdisk', ramdisk, '--dtb', parts / 'dtb',
     '--recovery_dtbo', parts / 'recovery_dtbo', '--cmdline', cmdline, '--output', output])
avbtool = rom / 'out/host/linux-x86/bin/avbtool'
run([avbtool, 'add_hash_footer', '--image', output, '--partition_name', 'recovery',
     '--partition_size', config['partition_size'], '--algorithm', 'SHA256_RSA4096',
     '--key', rom / 'external/avb/test/data/testkey_rsa4096.pem'])
run([avbtool, 'verify_image', '--image', output], stdout=subprocess.PIPE)
verified = build / 'verified'
run([sys.executable, rom / 'system/tools/mkbootimg/unpack_bootimg.py',
     '--boot_img', output, '--out', verified], stdout=subprocess.DEVNULL)
for name in ('kernel', 'dtb', 'recovery_dtbo'):
    assert sha(parts / name) == sha(verified / name)
assert sha(ramdisk) == sha(verified / 'ramdisk')
target = destination / ('lineage-24.0-sheng-recovery-' + args.revision + '.img')
shutil.copyfile(output, target)
assert sha(target) == sha(output)
report = {'revision': args.revision, 'image': target.name, 'bytes': target.stat().st_size,
          'sha256': sha(target), 'source_r5_sha256': base['sha256'],
          'work_dir': str(build), 'changed_ui_files': changed,
          'qti_backend': qti, 'kernel_dtb_dtbo_unchanged_from_r5': True,
          'cmdline': cmdline, 'static_preinit_sha256': sha(root / 'init'), 'avb_verified': True,
          'hardware_tested': False, 'commands': commands}
(destination / 'recovery-build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(destination / 'SHA256SUMS').write_text(f"{report['sha256']}  {target.name}\n")
(work / 'reports' / ('recovery-' + args.revision + '.json')).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: report[key] for key in ('image', 'sha256', 'bytes', 'changed_ui_files')}, indent=2))
