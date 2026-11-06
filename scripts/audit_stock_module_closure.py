#!/usr/bin/env python3
"""Resolve stock module providers against the actually built Lineage kernel ABI."""
from collections import defaultdict, deque
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
stock = rom.parent / 'firmware-dump/hardware/modules'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--all-stock', action='store_true')
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('sheng_module', work / 'device/xiaomi/sheng/kernel/stock-modules/stage.py')
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)
core = {}
for line in (rom / 'out/target/product/sheng/obj/KERNEL_OBJ/Module.symvers').read_text().splitlines():
    fields = line.split()
    if len(fields) >= 3 and fields[2] == 'vmlinux':
        core[fields[1]] = int(fields[0], 16)
modules, duplicate_files = {}, []
providers = defaultdict(list)
for file in sorted(stock.rglob('*.ko')):
    module = abi.Module(file)
    item = {'path': str(file), 'sha256': hashlib.sha256(module.data).hexdigest(),
            'imports': module.imports(), 'exports': module.exports(), 'info': module.info}
    name = file.name
    if name in modules:
        old = modules[name]
        if item['sha256'] != old['sha256']:
            duplicate_files.append({'module': name, 'first': old['path'], 'other': item['path'],
                                    'abi_identical': item['imports'] == old['imports'] and item['exports'] == old['exports']})
        continue
    modules[name] = item
    for symbol, crc in item['exports'].items():
        providers[symbol].append((name, crc))
roots = [line.split()[1] for line in (work / 'device/xiaomi/sheng/configs/modules/stock-modules.list').read_text().splitlines()
         if line.strip() and not line.startswith('#')]
if args.all_stock:
    roots = sorted(modules)
queue = deque(roots)
selected, dependencies, errors = set(), defaultdict(set), []
while queue:
    name = queue.popleft()
    if name in selected:
        continue
    assert name in modules, f'Missing stock module {name}'
    selected.add(name)
    item = modules[name]
    for symbol, crc in item['exports'].items():
        if symbol in core:
            errors.append({'module': name, 'symbol': symbol, 'reason': 'duplicates-built-in-kernel-export'})
    for symbol, expected in item['imports'].items():
        if symbol in core:
            if core[symbol] != expected:
                errors.append({'module': name, 'symbol': symbol, 'reason': 'kernel-crc-mismatch',
                               'stock_crc': hex(expected), 'built_crc': hex(core[symbol])})
            continue
        candidates = [provider for provider, crc in providers[symbol] if crc == expected]
        if len(candidates) == 1:
            provider = candidates[0]
            if provider != name:
                dependencies[name].add(provider)
                queue.append(provider)
        else:
            errors.append({'module': name, 'symbol': symbol,
                           'reason': 'no-matching-stock-provider' if not candidates else 'ambiguous-stock-provider',
                           'stock_crc': hex(expected), 'candidates': candidates,
                           'other_provider_crcs': [{'module': p, 'crc': hex(c)} for p, c in providers[symbol]]})
report = {'built_kernel_export_count': len(core), 'stock_module_names': len(modules),
          'roots': roots, 'closure': sorted(selected),
          'dependencies': {name: sorted(values) for name, values in sorted(dependencies.items())},
          'closure_inputs': {name: {'path': modules[name]['path'], 'sha256': modules[name]['sha256']}
                             for name in sorted(selected)},
          'errors': errors, 'duplicate_stock_files_with_different_hashes': duplicate_files,
          'automatic_changes': False, 'rom_compiled': False}
destination = 'stock-all-module-abi.json' if args.all_stock else 'stock-module-closure.json'
(work / 'reports' / destination).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'built_kernel_export_count': len(core), 'stock_module_names': len(modules),
                 'closure_module_count': len(selected), 'errors': errors,
                 'duplicate_stock_files_with_different_hashes': duplicate_files}, indent=2))
