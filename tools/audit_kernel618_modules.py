#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read sheng modules without changing them; optionally check a built kernel ABI.

Inventory success is not kernel compatibility. A candidate check includes
module_layout, missing providers, duplicate exports and this_module size.
The candidate must supply its own zram/zsmalloc modules, config and symvers.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct


class ElfModule:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self.digest = hashlib.sha256(self.data).hexdigest()
        data = self.data
        if data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 183:
            raise ValueError(f'Expected little-endian ELF64 AArch64: {path}')
        shoff = struct.unpack_from('<Q', data, 40)[0]
        size, count, strings = struct.unpack_from('<HHH', data, 58)
        if size != 64 or not count or shoff + count * size > len(data):
            raise ValueError(f'Invalid section headers: {path}')
        self.sections = [struct.unpack_from('<IIQQQQIIQQ', data, shoff + i * size)
                         for i in range(count)]
        names = self.section_bytes(self.sections[strings])
        self.named = {self.cstring(names, s[0]): s for s in self.sections}
        self.info = defaultdict(list)
        for item in self.get('.modinfo').split(b'\0'):
            if b'=' in item:
                key, value = item.split(b'=', 1)
                self.info[key.decode()].append(value.decode())

    @staticmethod
    def cstring(data, offset):
        return data[offset:data.index(b'\0', offset)].decode()

    def section_bytes(self, sec):
        off, size = sec[4:6]
        if off + size > len(self.data):
            raise ValueError(f'Section outside ELF: {self.path}')
        return self.data[off:off + size]

    def get(self, name):
        return self.section_bytes(self.named[name]) if name in self.named else b''

    def versions(self):
        basic = self.get('__versions')
        if len(basic) % 64:
            raise ValueError(f'Invalid basic modversions: {self.path}')
        versions = {self.cstring(basic, off + 8): struct.unpack_from('<Q', basic, off)[0] & 0xffffffff
                    for off in range(0, len(basic), 64)}
        has_names = '__version_ext_names' in self.named
        has_crcs = '__version_ext_crcs' in self.named
        if has_names or has_crcs:
            names = self.get('__version_ext_names').rstrip(b'\0').split(b'\0')
            crcs = self.get('__version_ext_crcs')
            if not has_names or not has_crcs or len(crcs) != len(names) * 4:
                raise ValueError(f'Invalid extended modversions: {self.path}')
            for i, name in enumerate(names):
                name = name.decode()
                crc = struct.unpack_from('<I', crcs, i * 4)[0]
                if name in versions and versions[name] != crc:
                    raise ValueError(f'Conflicting modversions: {self.path}: {name}')
                versions[name] = crc
        return versions

    def symbols(self):
        table = self.named.get('.symtab')
        if table is None:
            raise ValueError(f'Missing symbol table: {self.path}')
        data = self.section_bytes(table)
        names = self.section_bytes(self.sections[table[6]])
        if table[9] != 24 or len(data) % 24:
            raise ValueError(f'Invalid symbol table: {self.path}')
        for off in range(0, len(data), 24):
            name, info, _, index, value, _ = struct.unpack_from('<IBBHQQ', data, off)
            yield self.cstring(names, name), info, index, value

    def exports(self):
        result = {}
        for name, _, index, value in self.symbols():
            if not name.startswith('__crc_'):
                continue
            if index == 0xfff1:  # 5.15 genksyms: SHN_ABS
                crc = value & 0xffffffff
            elif 0 < index < len(self.sections):  # newer section-backed CRCs
                data = self.section_bytes(self.sections[index])
                crc = struct.unpack_from('<I', data, value)[0]
            else:
                raise ValueError(f'Unresolved CRC definition: {self.path}: {name}')
            result[name[6:]] = crc
        return result

    def undefined(self):
        return {name for name, info, index, _ in self.symbols()
                if index == 0 and info >> 4 == 1 and name}  # required GLOBAL; weak can be null

    @property
    def layout_size(self):
        sec = self.named.get('.gnu.linkonce.this_module')
        return sec[5] if sec else None


def inventory(stock_root, plan):
    wanted = plan['stock_modules_sha256']
    modules, duplicates = {}, []
    for path in sorted(stock_root.rglob('*.ko')):
        if path.name not in wanted:
            continue
        module = ElfModule(path)
        if module.digest != wanted[path.name]:
            raise ValueError(f'Stock hash differs from module-plan.json: {path}')
        if path.name in modules:
            duplicates.append(str(path))
        modules[path.name] = module
    missing = sorted(set(wanted) - set(modules))
    if missing:
        raise ValueError(f'Missing stock modules: {missing}')
    rows = {}
    for name, module in modules.items():
        versions = module.versions()
        rows[name] = {
            'path': str(module.path), 'sha256': module.digest,
            'vermagic': module.info['vermagic'], 'depends': module.info['depends'],
            'aliases': module.info['alias'], 'imports': len(versions),
            'module_layout_crc': versions.get('module_layout'),
            'this_module_bytes': module.layout_size,
        }
    return modules, {
        'stock_module_count': len(modules), 'stock_inputs_hash_verified': True,
        'identical_duplicate_paths': duplicates,
        'vermagic_counts': dict(Counter(v for m in modules.values() for v in m.info['vermagic'])),
        'this_module_size_counts': dict(Counter(m.layout_size for m in modules.values())),
        'stock_modules': rows,
    }


def check_candidate(modules, plan, kernel_out, gki_paths, series):
    config = (kernel_out / '.config').read_text().splitlines()
    release = (kernel_out / 'include/config/kernel.release').read_text().strip()
    issues = []
    warnings = []
    if not release.startswith(series + '.'):
        issues.append({'kind': 'wrong_kernel_series', 'release': release, 'expected': series})
    if 'CONFIG_MODVERSIONS=y' not in config:
        issues.append({'kind': 'modversions_disabled'})
    replacements = {p.name: ElfModule(p) for p in gki_paths}
    if len(replacements) != len(gki_paths) or set(replacements) != set(plan['source_keep_modules']):
        raise ValueError('Supply exactly one candidate zram.ko and zsmalloc.ko')
    effective = {**modules, **replacements}
    providers = defaultdict(list)
    for line in (kernel_out / 'Module.symvers').read_text().splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[2] == 'vmlinux':
            providers[fields[1]].append(('vmlinux', int(fields[0], 16)))
    for name, module in effective.items():
        for symbol, crc in module.exports().items():
            providers[symbol].append((name, crc))
    for symbol, entries in providers.items():
        if len(entries) != 1:
            issues.append({'kind': 'duplicate_export', 'symbol': symbol, 'providers': entries})
    reference = replacements[plan['source_keep_modules'][0]]
    reference_vermagic = reference.info['vermagic'][0].split()
    # With MODVERSIONS the loader ignores the release token; it still checks flags.
    flags = reference_vermagic[1:]
    checked = 0
    for name, module in effective.items():
        info = module.info['vermagic']
        if len(info) != 1 or info[0].split()[1:] != flags or 'modversions' not in flags:
            issues.append({'kind': 'vermagic_flags', 'module': name, 'vermagic': info})
        if name in replacements and (len(info) != 1 or info[0].split()[0] != release):
            issues.append({'kind': 'stale_candidate_module', 'module': name, 'release': release})
        if not reference.layout_size or module.layout_size != reference.layout_size:
            issues.append({'kind': 'this_module_size', 'module': name,
                           'bytes': module.layout_size, 'expected': reference.layout_size})
        versions = module.versions()
        if not versions or 'module_layout' not in versions:
            issues.append({'kind': 'missing_module_layout_version', 'module': name})
        for symbol, crc in versions.items():
            entries = providers.get(symbol, [])
            checked += 1
            if not entries:
                issues.append({'kind': 'missing_provider', 'module': name, 'symbol': symbol})
            elif len(entries) == 1 and entries[0][1] != crc:
                issues.append({'kind': 'crc_mismatch', 'module': name, 'symbol': symbol,
                               'import_crc': crc, 'provider': entries[0]})
        for symbol in module.undefined() - set(versions):
            if symbol not in providers:
                issues.append({'kind': 'missing_unversioned_provider', 'module': name, 'symbol': symbol})
            else:
                # The real loader accepts an import missing from __versions if
                # its export resolves. Its ABI cannot be established by CRC.
                warnings.append({'kind': 'unversioned_global_import', 'module': name, 'symbol': symbol})
    return {
        'release': release, 'expected_series': series,
        'symvers_sha256': hashlib.sha256((kernel_out / 'Module.symvers').read_bytes()).hexdigest(),
        'effective_module_count': len(effective), 'versioned_imports_checked': checked,
        'issue_counts': dict(Counter(x['kind'] for x in issues)),
        'issue_count': len(issues), 'issues': issues[:80],
        'issues_truncated': len(issues) > 80, 'warnings': warnings,
        'abi_passed': not issues,
        'scope': 'Static ELF/CRC checks only; signatures, namespaces, DT binding and hardware require further validation.',
    }


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock-root', type=Path, required=True)
    parser.add_argument('--module-plan', type=Path, default=project / 'device/xiaomi/sheng/interfaces/kernel/stock-modules/module-plan.json')
    parser.add_argument('--kernel-out', type=Path)
    parser.add_argument('--gki-module', type=Path, action='append', default=[])
    parser.add_argument('--expect-series', default='6.18')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.module_plan.read_text())
    modules, result = inventory(args.stock_root, plan)
    result.update(schema=1, stock_firmware=plan['stock_firmware'],
                  stock_root=str(args.stock_root),
                  stock_inventory_fingerprint=hashlib.sha256(
                      json.dumps(result['stock_modules'], sort_keys=True).encode()).hexdigest(),
                  device='sheng', source_inputs_modified=False, device_writes=0,
                  kernel618_ready=False, physical_device_validated=False)
    if args.kernel_out:
        candidate = check_candidate(modules, plan, args.kernel_out, args.gki_module, args.expect_series)
        result['candidate'] = candidate
        result['status'] = 'static_abi_passed' if candidate['abi_passed'] else 'static_abi_failed'
        # Candidate reports share the verified inventory fingerprint; avoid
        # duplicating hundreds of module metadata entries in every comparison.
        del result['stock_modules']
    else:
        if args.gki_module:
            parser.error('--gki-module requires --kernel-out')
        result['status'] = 'inventory_only_no_candidate'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'stock_module_count', 'kernel618_ready')}))
    if 'candidate' in result:
        print(json.dumps({k: result['candidate'][k] for k in ('release', 'versioned_imports_checked', 'issue_counts', 'abi_passed')}))
        return 0 if result['candidate']['abi_passed'] else 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
