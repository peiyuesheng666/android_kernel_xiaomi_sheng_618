#!/usr/bin/env python3
"""Exercise real BSP staging, repeatability, and rejection before mutation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
out = rom / 'out/target/product/sheng/obj/KERNEL_OBJ'
release = (out / 'include/config/kernel.release').read_text().strip()
source = rom / 'out/target/product/sheng/obj/PACKAGING/kernel_modules_intermediates/lib/modules' / release
plan = work / 'device/xiaomi/sheng/kernel/stock-modules/module-plan.json'
stage = plan.parent / 'stage.py'
log = rom.parent / 'logs/verify-stock-bsp-guard.log'


def checksums(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*.ko')}


with tempfile.TemporaryDirectory(prefix='sheng-bsp-staging-') as temporary, log.open('w') as output:
    directory = Path(temporary)
    kernel = directory / 'kernel'
    (kernel / 'include/config').mkdir(parents=True)
    (kernel / 'include/config/kernel.release').write_text(release + '\n')
    shutil.copyfile(out / 'Module.symvers', kernel / 'Module.symvers')
    install = directory / 'install'
    target = install / 'lib/modules' / release
    for file in source.rglob('*.ko'):
        destination = target / file.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.link(file, destination)
    command = [sys.executable, str(stage), '--kernel-out', str(kernel), '--install-root', str(install),
               '--stock-dir', str(rom / 'device/xiaomi/sheng-kernel/stock-modules'), '--module-plan', str(plan)]
    result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
    assert result.returncode == 0, f'Real BSP staging failed; see {log}'
    passed = json.loads((kernel / 'sheng-stock-module-compatibility.json').read_text())
    assert not passed['errors'] and passed['effective_modules_checked'] == 419
    first = checksums(target)
    assert len(first) == 419
    result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
    assert result.returncode == 0 and checksums(target) == first, 'Staging was not repeatable'
    lines = (kernel / 'Module.symvers').read_text().splitlines(True)
    changed = False
    for index, line in enumerate(lines):
        fields = line.split()
        if len(fields) >= 3 and fields[1:3] == ['module_layout', 'vmlinux']:
            lines[index] = line.replace(fields[0], f'0x{int(fields[0], 16) ^ 1:08x}', 1)
            changed = True
            break
    assert changed
    (kernel / 'Module.symvers').write_text(''.join(lines))
    result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
    rejected = json.loads((kernel / 'sheng-stock-module-compatibility.json').read_text())
    assert result.returncode != 0 and any('CRC mismatch for module_layout' in error for error in rejected['errors'])
    assert checksums(target) == first, 'Rejected ABI changed staged module contents'
report = {'real_effective_modules_checked': passed['effective_modules_checked'],
          'stock_modules': len(passed['modules']), 'source_gki_modules': passed['source_modules_checked'],
          'real_staging_passed': True, 'repeat_staging_preserves_contents': True,
          'bad_kernel_crc_rejected_without_staging_mutation': True, 'log': str(log),
          'full_validation_run_passed': False, 'rom_compiled': False}
(work / 'reports/stock-bsp-guard-tests.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
