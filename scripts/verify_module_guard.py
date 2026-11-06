#!/usr/bin/env python3
"""Exercise the ABI installer with a real stock module and synthetic symvers.

This checks the guard itself, not compatibility with the not-yet-built kernel.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

work = Path(__file__).resolve().parents[1]
stage = work / 'device/xiaomi/sheng/kernel/stock-modules/stage.py'
spec = importlib.util.spec_from_file_location('sheng_abi_guard', stage)
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)
module = Path('/root/sheng-lineage/lineage-24.0/device/xiaomi/sheng-kernel/stock-modules/fpc1552.ko')
imports = abi.Module(module).imports()
assert 'module_layout' in imports
results = []
with tempfile.TemporaryDirectory(prefix='sheng-abi-guard-') as temporary:
    root = Path(temporary)
    stock = root / 'stock'
    stock.mkdir()
    (stock / module.name).symlink_to(module)
    for mismatch in (False, True):
        case = root / ('mismatch' if mismatch else 'matching')
        out = case / 'kernel'
        (out / 'include/config').mkdir(parents=True)
        (out / 'include/config/kernel.release').write_text('5.15.211-synthetic-test\n')
        (out / 'Module.symvers').write_text(''.join(
            f'{(crc ^ 1 if mismatch and symbol == "module_layout" else crc):#010x}\t{symbol}\tvmlinux\tEXPORT_SYMBOL\n'
            for symbol, crc in imports.items()))
        install = case / 'install'
        (install / 'lib/modules/5.15.211-synthetic-test').mkdir(parents=True)
        run = subprocess.run([sys.executable, str(stage), '--kernel-out', str(out),
                              '--install-root', str(install), '--stock-dir', str(stock)],
                             capture_output=True, text=True)
        report = json.loads((out / 'sheng-stock-module-compatibility.json').read_text())
        if mismatch:
            assert run.returncode != 0 and any('CRC mismatch for module_layout' in e for e in report['errors'])
            assert not list(install.rglob('*.ko')), 'Rejected module must not be installed'
        else:
            assert run.returncode == 0, run.stdout + run.stderr
            assert (install / 'lib/modules/5.15.211-synthetic-test/extra/sheng' / module.name).is_file()
        results.append({'fixture': 'wrong_crc' if mismatch else 'matching_crc', 'expected_behavior_verified': True})
(work / 'reports/module-guard-tests.json').write_text(json.dumps({
    'guard_test_passed': True, 'actual_built_kernel_abi_validated': False, 'results': results}, indent=2) + '\n')
print('ABI guard tests passed: accepts matching fixture, rejects bad CRC without installing it.')
