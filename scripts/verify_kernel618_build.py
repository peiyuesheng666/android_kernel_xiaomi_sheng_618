#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify real 6.18 outputs and module closure; never infer sheng boot support."""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from audit_kernel618_modules import ElfModule


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def main():
    project = Path(__file__).resolve().parents[1]
    plan = json.loads((project / 'device/xiaomi/sheng/interfaces/kernel/6.18/source-plan.json').read_text())
    root = Path(plan['build_root'])
    source = root / 'src/ack'
    out = root / 'out/ack-arm64'
    dist = root / 'out/ack-dist'
    release = (out / 'include/config/kernel.release').read_text().strip()
    assert release.startswith('6.18.')
    assert run('git', '-C', str(source), 'rev-parse', 'HEAD') == plan['kernel_core']['revision']
    assert not run('git', '-C', str(source), 'status', '--porcelain')
    assert (root / 'logs/build-status.txt').read_text().strip() == 'complete'
    config = (out / '.config').read_text().splitlines()
    required = ['CONFIG_RUST=y', 'CONFIG_MODVERSIONS=y', 'CONFIG_GENDWARFKSYMS=y',
                'CONFIG_DEBUG_INFO_BTF=y', 'CONFIG_ANDROID_BINDER_IPC_RUST=m']
    assert all(x in config for x in required)
    image = (dist / 'Image').read_bytes()
    assert image[56:60] == b'ARM\x64'
    assert gzip.decompress((dist / 'Image.gz').read_bytes()) == image
    for name, original in [('Image', out / 'arch/arm64/boot/Image'),
                           ('Image.gz', out / 'arch/arm64/boot/Image.gz'),
                           ('Module.symvers', out / 'Module.symvers'),
                           ('ack.config', out / '.config')]:
        assert sha(dist / name) == sha(original)
    installed = dist / 'module-staging/lib/modules' / release
    module_paths = sorted(installed.rglob('*.ko'))
    assert module_paths
    baseline_count = len(module_paths)
    ports = {'clock': ['clk-qcom.ko', 'tcsrcc-kalama.ko'],
             'pogo': ['xm_utils.ko'], 'cs35l43': ['cs35l43_dlkm.ko']}
    port_sources = {}
    source_specs = plan['board_sources'] + plan.get('supplemental_board_sources', [])
    source_paths = {x['url']: root / 'src' / x['name'] for x in source_specs}
    checked_sources = set()
    for group, names in ports.items():
        port_dir = root / 'ports' / group
        receipt = json.loads((port_dir / 'source-receipt.json').read_text())
        for name, expected in receipt['generated_sha256'].items():
            assert sha(port_dir / name) == expected
        for record in receipt['source_files']:
            repo = source_paths.get(record['repository'], Path(record['repository']))
            identity = (str(repo), record['revision'])
            if identity not in checked_sources:
                assert run('git', '-C', str(repo), 'rev-parse', 'HEAD') == record['revision']
                assert not run('git', '-C', str(repo), 'status', '--porcelain')
                checked_sources.add(identity)
            assert sha(repo / record['path']) == record['source_sha256']
        port_sources[group] = receipt
        module_paths += [port_dir / name for name in names]
    modules = {}
    providers = defaultdict(list)
    export_policy = {}
    for symvers in [out / 'Module.symvers', *[root / 'ports' / group / 'Module.symvers' for group in ports]]:
        for line in symvers.read_text().splitlines():
            fields = line.split()
            if len(fields) >= 4:
                export_policy[fields[1]] = (fields[3], fields[4] if len(fields) > 4 else '')
                if fields[2] == 'vmlinux':
                    providers[fields[1]].append(('vmlinux', int(fields[0], 16)))
    for path in module_paths:
        key = path.stem.replace('-', '_')
        assert key not in modules, f'Duplicate module name: {path}'
        module = ElfModule(path)
        modules[key] = module
        for symbol, crc in module.exports().items():
            providers[symbol].append((key, crc))
    issues, rows, imports = [], {}, 0
    for symbol, entries in providers.items():
        if len(entries) != 1:
            issues.append({'kind': 'duplicate_export', 'symbol': symbol})
    expected_layout = modules['zram'].layout_size
    flags = modules['zram'].info['vermagic'][0].split()[1:]
    graph = {}
    for name, module in modules.items():
        versions = module.versions()
        assert len(module.info['vermagic']) == 1
        assert module.info['vermagic'][0].split() == [release, *flags], module.path
        assert module.layout_size == expected_layout
        assert 'module_layout' in versions
        imported_namespaces = set(module.info['import_ns'])
        for symbol, crc in versions.items():
            imports += 1
            entries = providers.get(symbol, [])
            if len(entries) != 1 or entries[0][1] != crc:
                issues.append({'kind': 'provider_or_crc', 'module': name, 'symbol': symbol})
        for symbol in module.undefined():
            if symbol not in providers:
                issues.append({'kind': 'undefined_symbol', 'module': name, 'symbol': symbol})
            _, namespace = export_policy.get(symbol, ('', ''))
            # Module-specific namespace allowlists are handled by modpost;
            # ordinary symbol namespaces must be imported explicitly.
            if namespace and not namespace.startswith('module:') and namespace not in imported_namespaces:
                issues.append({'kind': 'namespace', 'module': name, 'symbol': symbol, 'namespace': namespace})
        depends = [d.replace('-', '_') for value in module.info['depends'] for d in value.split(',') if d]
        graph[name] = depends
        for dep in depends:
            if dep not in modules:
                issues.append({'kind': 'missing_module_dependency', 'module': name, 'dependency': dep})
        signed = module.data.endswith(b'~Module signature appended~\n')
        if module.path.is_relative_to(installed) and not signed:
            issues.append({'kind': 'unsigned_installed_baseline_module', 'module': name})
        rows[name] = {'path': str(module.path), 'sha256': module.digest,
                      'versioned_imports': len(versions), 'depends': depends,
                      'aliases': module.info['alias'], 'signed_trailer_present': signed}
    ordered, visiting, visited = [], set(), set()

    def visit(name):
        if name in visiting:
            raise ValueError(f'Module dependency cycle at {name}')
        if name in visited or name not in graph:
            return
        visiting.add(name)
        for dep in graph[name]:
            visit(dep)
        visiting.remove(name)
        visited.add(name)
        ordered.append(name)

    for name in graph:
        visit(name)
    sdk = Path('/root/sheng-lineage/lineage-24.0/prebuilts')
    tools = {'clang': sdk / 'clang/host/linux-x86/clang-r584948b/bin/clang',
             'rustc': sdk / 'rust-toolchain/linux-x86/1.91.1/bin/rustc',
             'bindgen': sdk / 'clang-tools/linux-x86/bin/bindgen',
             'pahole': sdk / 'kernel-build-tools/linux_musl-x86/bin/pahole'}
    result = {'schema': 1, 'date': '2026-11-08', 'device': 'sheng', 'release': release,
              'ack_revision': plan['kernel_core']['revision'], 'source_clean': True,
              'build_root': str(root), 'baseline_build_complete': True,
              'image_arm64_header_verified': True, 'image_gzip_roundtrip_verified': True,
              'configuration_checks': required, 'baseline_module_count': baseline_count,
              'port_module_count': sum(map(len, ports.values())), 'versioned_imports_checked': imports,
              'this_module_bytes': expected_layout, 'static_module_closure_passed': not issues,
              'issue_counts': dict(Counter(x['kind'] for x in issues)), 'issues': issues[:80],
              'toolchains': {name: {'path': str(path), 'sha256': sha(path),
                                    'version': run(str(path), '--version').splitlines()[0]}
                             for name, path in tools.items()},
              'host_elfutils': {'version': '0.193', 'system_libraries_changed': False,
                               'gendwarfksyms_ldd': run('ldd', str(out / 'scripts/gendwarfksyms/gendwarfksyms'))},
              'artifacts': {name: {'path': str(dist / name), 'bytes': (dist / name).stat().st_size,
                                   'sha256': sha(dist / name)}
                            for name in ('Image', 'Image.gz', 'Module.symvers', 'System.map', 'ack.config')},
              'port_source_receipts': port_sources,
              'modules': rows, 'dependency_order': ordered,
              'device_port_complete': False, 'boot_image_created': False,
              'device_writes': 0, 'physical_device_validated': False,
              'limits': ['Compile/static checks do not establish hardware support.',
                         'Port modules have not been installed or signed.',
                         'Installed baseline signature trailers were detected, not cryptographically verified.',
                         'Clang r584948b and Rust 1.91.1 differ from ACK recommended r584948c and 1.91.1.p3; no madrid KMI compatibility claimed.']}
    target = project / 'reports/kernel618-build-verification.json'
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: result[k] for k in ('release', 'baseline_module_count', 'port_module_count',
                                           'versioned_imports_checked', 'static_module_closure_passed', 'issue_counts')}))
    return 0 if not issues else 1


if __name__ == '__main__':
    raise SystemExit(main())
