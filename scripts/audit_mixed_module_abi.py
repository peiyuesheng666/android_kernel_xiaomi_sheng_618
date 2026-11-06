#!/usr/bin/env python3
"""Resolve a consistent stock/source module mix before rebuilding anything."""
import contextlib
import argparse
import io
import json
import sys
from pathlib import Path

saved_arguments = sys.argv
sys.argv = [sys.argv[0]]
try:
    with contextlib.redirect_stdout(io.StringIO()):
        import audit_stock_module_closure as inventory
finally:
    sys.argv = saved_arguments
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stock-all', action='store_true')
parser.add_argument('--source-keep', nargs='*')
args = parser.parse_args()

work, rom, abi, core = inventory.work, inventory.rom, inventory.abi, inventory.core
out = rom / 'out/target/product/sheng/obj/KERNEL_OBJ'
release = (out / 'include/config/kernel.release').read_text().strip()
staging = rom / 'out/target/product/sheng/obj/PACKAGING/kernel_modules_intermediates/lib/modules' / release
source = {}
for file in sorted(staging.rglob('*.ko')):
    if file.is_relative_to(staging / 'extra/sheng'):
        continue
    assert file.name not in source, f'Duplicate source module basename: {file.name}'
    module = abi.Module(file)
    source[file.name] = {'path': str(file), 'imports': module.imports(), 'exports': module.exports()}
assert source
source_total = len(source)
excluded_source = []
if args.source_keep is not None:
    assert set(args.source_keep) <= set(source), 'A requested source module was not built'
    excluded_source = sorted(set(source) - set(args.source_keep))
    source = {name: source[name] for name in args.source_keep}
selected = set(inventory.modules) if args.stock_all else set(inventory.selected)
if args.source_keep is not None:
    selected.difference_update(args.source_keep)
history, remaining = [], []


def close_stock(names):
    queue = list(names)
    additions = set()
    while queue:
        name = queue.pop()
        if name in selected or name in additions:
            continue
        additions.add(name)
        for symbol, crc in inventory.modules[name]['imports'].items():
            if symbol in core:
                continue
            candidates = [p for p, c in inventory.providers[symbol] if c == crc]
            if len(candidates) == 1:
                queue.extend(candidates)
    return additions


for iteration in range(len(inventory.modules) + 1):
    effective = dict(source)
    effective.update({name: inventory.modules[name] for name in selected})
    exports = {symbol: [('<vmlinux>', crc)] for symbol, crc in core.items()}
    for name, module in effective.items():
        for symbol, crc in module['exports'].items():
            exports.setdefault(symbol, []).append((name, crc))
    remaining = []
    replace = set()
    for name, module in effective.items():
        for symbol, crc in module['imports'].items():
            providers = exports.get(symbol, [])
            if len(providers) == 1 and providers[0][1] == crc:
                continue
            remaining.append({'module': name, 'stock': name in selected, 'symbol': symbol,
                              'expected_crc': hex(crc),
                              'providers': [{'module': p, 'crc': hex(c)} for p, c in providers]})
            if name not in selected and name in inventory.modules and name not in (args.source_keep or []):
                replace.add(name)
    duplicates = [{'symbol': symbol, 'providers': [{'module': p, 'crc': hex(c)} for p, c in values]}
                  for symbol, values in exports.items() if len(values) > 1]
    additions = close_stock(replace)
    history.append({'iteration': iteration, 'stock_modules': len(selected),
                    'import_errors': len(remaining), 'duplicate_exports': len(duplicates),
                    'add_stock_modules': sorted(additions)})
    if not additions:
        break
    selected.update(additions)
report = {'kernel_release': release, 'source_modules': len(source), 'source_inventory_total': source_total,
          'excluded_source_modules': excluded_source, 'stock_modules': sorted(selected),
          'source_replacement_names': sorted(set(source) & selected), 'iterations': history,
          'errors': remaining, 'duplicate_exports': duplicates,
          'effective_mix_passed': not remaining and not duplicates,
          'stock_inputs': {name: {'path': inventory.modules[name]['path'], 'sha256': inventory.modules[name]['sha256']}
                           for name in sorted(selected)},
          'automatic_changes': False, 'rom_compiled': False}
destination = 'stock-bsp-module-abi.json' if args.stock_all else 'mixed-module-abi.json'
(work / 'reports' / destination).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'source_modules': len(source), 'stock_module_count': len(selected),
                 'source_replacement_count': len(set(source) & selected), 'iterations': history,
                 'errors': remaining, 'duplicate_exports': duplicates,
                 'effective_mix_passed': report['effective_mix_passed']}, indent=2))
