#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the exported first-boot Image against its build and complete module layer."""
import json
from pathlib import Path

from audit_kernel618_modules import ElfModule, check_candidate
from build_sheng618_upstream import PROJECT, K618, OUT, sha


def main():
    path = PROJECT / 'reports/kernel618-upstream-image.json'
    report = json.loads(path.read_text())
    exported = Path(report['image'])
    built = K618 / 'out-gki-ir/arch/arm64/boot/Image'
    assert exported.read_bytes()[56:60] == b'ARM\x64'
    assert sha(exported) == sha(built) == report['sha256']
    assert exported.stat().st_size == report['bytes']
    source_layer = K618 / 'boot-test/stage/overlay.cpio'
    assert sha(source_layer) == sha(K618 / 'boot-test/initramfs.cpio')
    config = (K618 / 'out-gki-ir/.config').read_text().splitlines()
    assert '# CONFIG_INITRAMFS_FORCE is not set' in config
    assert 'CONFIG_INITRAMFS_SOURCE="' + str(K618 / 'boot-test/initramfs.cpio') + '"' in config
    expected = sorted(line for line in (OUT / 'Module.symvers').read_text().splitlines()
                      if line.split()[2] == 'vmlinux')
    assert expected == sorted((K618 / 'out-gki-ir/vmlinux.symvers').read_text().splitlines())
    stage = K618 / 'boot-test/stage/rd/lib/modules'
    modules = {p.name: ElfModule(p) for p in stage.glob('*.ko')}
    dependencies = stage / 'modules.dep'
    listed = {Path(line.split(':', 1)[0]).name for line in dependencies.read_text().splitlines()}
    assert set(modules) == listed
    for module in modules.values():
        for value in module.info['depends']:
            for name in filter(None, value.split(',')):
                assert name.replace('-', '_') in {p[:-3].replace('-', '_') for p in modules}
    checked = check_candidate(modules, {'source_keep_modules': ['zram.ko', 'zsmalloc.ko']}, OUT,
                              [stage / 'zram.ko', stage / 'zsmalloc.ko'], '6.18')
    assert checked['abi_passed'], checked['issue_counts']
    assert len(modules) == report['module_count']
    report.update(module_dependencies_sha256=sha(dependencies),
                  versioned_imports_checked=checked['versioned_imports_checked'],
                  kernel_exports_checked=len(expected),
                  exported_image_verified=True,
                  known_incomplete_tablet_drivers=['nt36532_touch', 'metis', 'nanosic_driver',
                                                   'xiaomi_keyboard_driver', 'xiaomi_hall'])
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({key: report[key] for key in ['image', 'bytes', 'sha256', 'module_count',
                     'versioned_imports_checked', 'exported_image_verified', 'runtime_validated']},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
