#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Install stock-only board modules after checking their real symbol CRCs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

from touch_boot_delay import patch_bytes


class Module:
    def __init__(self, path, data=None):
        self.path = Path(path)
        self.data = self.path.read_bytes() if data is None else data
        assert self.data[:6] == b'\x7fELF\x02\x01', f'Expected ELF64 little endian: {path}'
        assert struct.unpack_from('<H', self.data, 18)[0] == 183, f'Expected AArch64: {path}'
        shoff = struct.unpack_from('<Q', self.data, 40)[0]
        entsize, count, strings_index = struct.unpack_from('<HHH', self.data, 58)
        assert entsize == 64 and shoff + count * 64 <= len(self.data)
        self.sections = [struct.unpack_from('<IIQQQQIIQQ', self.data, shoff + n * 64) for n in range(count)]
        names = self.section_data(self.sections[strings_index])
        self.named = {self.string(names, s[0]): s for s in self.sections}
        info = self.section_data(self.named['.modinfo']).split(b'\0')
        self.info = {}
        for item in info:
            if b'=' in item:
                key, value = item.split(b'=', 1)
                self.info[key.decode()] = value.decode()

    @staticmethod
    def string(data, offset):
        return data[offset:data.index(b'\0', offset)].decode()

    def section_data(self, section):
        start, size = section[4:6]
        assert start + size <= len(self.data)
        return self.data[start:start + size]

    def imports(self):
        data = self.section_data(self.named['__versions'])
        assert len(data) % 64 == 0
        return {self.string(data, n + 8): struct.unpack_from('<Q', data, n)[0]
                for n in range(0, len(data), 64)}

    def exports(self):
        section = self.named.get('.symtab')
        if section is None:
            return {}
        names = self.section_data(self.sections[section[6]])
        data = self.section_data(section)
        assert section[9] == 24 and len(data) % 24 == 0
        result = {}
        for offset in range(0, len(data), 24):
            name, _, _, index, value, _ = struct.unpack_from('<IBBHQQ', data, offset)
            name = self.string(names, name)
            if index == 0xfff1 and name.startswith('__crc_'):
                result[name[6:]] = value
        return result


def stage_stock_bsp(args, release, target):
    plan = json.loads(args.module_plan.read_text())
    assert plan['schema'] == 1 and plan['strategy'] == 'stock-vendor-bsp-source-gki'
    stock = {p.name: Module(p) for p in sorted(args.stock_dir.glob('*.ko'))}
    assert set(stock) == set(plan['stock_modules_sha256'])
    for name, module in stock.items():
        assert hashlib.sha256(module.data).hexdigest() == plan['stock_modules_sha256'][name], f'Stock input changed: {name}'
    # Only transform a distribution copy after validating every OEM input. The
    # callback and module ABI stay identical; this removes a fixed 14-second wait.
    config = (args.kernel_out / '.config').read_text().splitlines()
    assert config.count('CONFIG_HZ=250') == 1, 'Touch boot delay requires audited HZ=250'
    touch = stock['nt36532_touch.ko']
    patched, touch_report = patch_bytes(touch.data, Module)
    stock['nt36532_touch.ko'] = Module(touch.path, data=patched)
    output = target / 'extra/sheng'
    source_files = [p for p in target.rglob('*.ko') if not p.is_relative_to(output)]
    source = {}
    for file in source_files:
        assert file.name not in source, f'Duplicate source module {file.name}'
        source[file.name] = Module(file)
    assert set(plan['source_keep_modules']) <= set(source), 'Required source GKI module missing'
    assert not set(plan['source_keep_modules']) & set(stock)
    effective = {name: source[name] for name in plan['source_keep_modules']}
    effective.update(stock)
    report = {'release': release, 'strategy': plan['strategy'], 'modules': sorted(stock),
              'board_module_transforms': [touch_report],
              'source_modules_checked': sorted(plan['source_keep_modules']),
              'effective_modules_checked': len(effective), 'errors': [],
              'pruned_generated_source_modules': sorted(set(source) - set(plan['source_keep_modules']))}
    exports = {}
    for line in (args.kernel_out / 'Module.symvers').read_text().splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[2] == 'vmlinux':
            exports[fields[1]] = (int(fields[0], 16), 'vmlinux')
    for name, module in effective.items():
        for symbol, crc in module.exports().items():
            if symbol in exports:
                report['errors'].append(f'{name}: duplicate export {symbol} with {exports[symbol][1]}')
            else:
                exports[symbol] = (crc, name)
    expected_flags = source[plan['source_keep_modules'][0]].info['vermagic'].split()[1:]
    for name, module in effective.items():
        if module.info.get('vermagic', '').split()[1:] != expected_flags or 'modversions' not in expected_flags:
            report['errors'].append(f'{name}: incompatible vermagic flags')
        for symbol, crc in module.imports().items():
            if symbol not in exports:
                report['errors'].append(f'{name}: unresolved {symbol}')
            elif exports[symbol][0] != crc:
                report['errors'].append(f'{name}: CRC mismatch for {symbol}: stock={crc:#x}, built={exports[symbol][0]:#x}')
    for file in output.glob('*.ko'):
        if file.name not in stock or hashlib.sha256(file.read_bytes()).hexdigest() not in (
                plan['stock_modules_sha256'][file.name], hashlib.sha256(stock[file.name].data).hexdigest()):
            report['errors'].append(f'{file.name}: stale or modified previous stock staging output')
    report_path = args.kernel_out / 'sheng-stock-module-compatibility.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    if report['errors']:
        for error in report['errors'][:30]:
            print(error)
        raise SystemExit(f'Board module ABI check failed ({len(report["errors"])} errors); see {report_path}')
    # Only distribution staging is pruned. Kernel source/build outputs stay intact.
    # The complete replacement set was checked before any staging mutation.
    for name, module in source.items():
        if name not in plan['source_keep_modules']:
            assert module.path.is_relative_to(target)
            module.path.unlink()
    output.mkdir(parents=True, exist_ok=True)
    for name, module in stock.items():
        (output / name).write_bytes(module.data)
    print(f'Validated {len(effective)} effective modules; staged {len(stock)} stock BSP modules and retained source GKI modules')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-out', type=Path, required=True)
    parser.add_argument('--install-root', type=Path, required=True)
    parser.add_argument('--stock-dir', type=Path, required=True)
    parser.add_argument('--module-plan', type=Path)
    args = parser.parse_args()
    release = (args.kernel_out / 'include/config/kernel.release').read_text().strip()
    assert release.startswith('5.15.'), f'Wrong LTS for stock board modules: {release}'
    target = args.install_root / 'lib/modules' / release
    assert target.is_dir(), f'Build platform modules first: {target}'
    if args.module_plan:
        stage_stock_bsp(args, release, target)
        return
    report = {'release': release, 'modules': [], 'errors': []}
    exports = {}
    for line in (args.kernel_out / 'Module.symvers').read_text().splitlines():
        fields = line.split()
        if len(fields) >= 2:
            exports[fields[1]] = int(fields[0], 16)
    for path in target.rglob('*.ko'):
        exports.update(Module(path).exports())
    selected = [Module(path) for path in sorted(args.stock_dir.glob('*.ko'))]
    assert selected, f'No prepared stock modules in {args.stock_dir}'
    for module in selected:
        for symbol, crc in module.exports().items():
            if symbol in exports and exports[symbol] != crc:
                report['errors'].append(f'{module.path.name}: conflicting export {symbol}')
            exports[symbol] = crc
    existing = {p.name for p in target.rglob('*.ko')}
    for module in selected:
        report['modules'].append(module.path.name)
        if module.path.name in existing:
            report['errors'].append(f'{module.path.name}: already source-built; remove prebuilt duplicate')
        if 'modversions' not in module.info.get('vermagic', ''):
            report['errors'].append(f'{module.path.name}: no modversions metadata')
        for symbol, crc in module.imports().items():
            if symbol not in exports:
                report['errors'].append(f'{module.path.name}: unresolved {symbol}')
            elif exports[symbol] != crc:
                report['errors'].append(f'{module.path.name}: CRC mismatch for {symbol}: stock={crc:#x}, built={exports[symbol]:#x}')
    report_path = args.kernel_out / 'sheng-stock-module-compatibility.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    if report['errors']:
        for error in report['errors'][:30]:
            print(error)
        raise SystemExit(f'Board module ABI check failed ({len(report["errors"])} errors); see {report_path}')
    output = target / 'extra/sheng'
    output.mkdir(parents=True, exist_ok=True)
    for module in selected:
        shutil.copyfile(module.path, output / module.path.name)
    print(f'Validated and staged {len(selected)} sheng board modules')


if __name__ == '__main__':
    main()
