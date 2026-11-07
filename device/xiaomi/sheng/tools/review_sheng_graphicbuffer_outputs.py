#!/usr/bin/env python3
"""Independently inspect real output instructions and reject invalid ABI/input fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from sheng_elf_compat import Elf

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
CLANG = ROM / 'prebuilts/clang/host/linux-x86/clang-r596125/bin'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--layout', type=Path, required=True)
    parser.add_argument('--outputs', type=Path, required=True)
    parser.add_argument('--flat', action='store_true')
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    rows = json.loads(args.inventory.read_text())
    tool = DEVICE / 'interfaces/compat/graphicbuffer/patch.py'
    reviewed, sites_total = [], 0
    for row in rows:
        if row['path'] == 'vendor/lib64/libgui_vendor.so':
            # The factory copy was inventoried but is not the installed provider.
            installed = ROM / 'out/target/product/sheng' / row['path']
            assert hashlib.sha256(installed.read_bytes()).hexdigest() == (
                '0b082826f4787ea3332e282e7c9de877c4e7384d388bdb68fdb7fbcdf0b231c3')
            continue
        source = Path(row['source'])
        target = args.outputs / (source.name if args.flat else row['path'])
        old, new = source.read_bytes(), target.read_bytes()
        assert hashlib.sha256(old).hexdigest() == row['sha256']
        assert len(old) == len(new) == row['bytes']
        elf = Elf(source)
        text = elf.sections['.text']
        allowed = set()
        for value in row['allocation_instructions']:
            address = int(value, 16)
            at = text[4] + address - text[3]
            allowed.update(range(at, at + 4))
        changed = {i for i, (a, b) in enumerate(zip(old, new)) if a != b}
        assert changed and changed <= allowed, row['path']
        disassemblies = []
        for label, path in [('before', source), ('after', target)]:
            dis = subprocess.check_output([CLANG / 'llvm-objdump', '-d', path], text=True)
            (args.work / (source.name + '-' + label + '.txt')).write_text(dis)
            constructors = re.findall(r'^\s*([0-9a-f]+): [0-9a-f]+\s+bl\s.*'
                                      r'<_ZN7android13GraphicBufferC[12]', dis, re.M)
            assert len(constructors) == row['direct_constructor_calls']
            disassemblies.append(constructors)
            for value in row['allocation_instructions']:
                immediate = '100' if label == 'before' else 'd30'
                assert re.search(rf'^\s*{int(value, 16):x}: [0-9a-f]+\s+mov\s+w0, #0x{immediate}\b',
                                 dis, re.M), (path, value)
        assert disassemblies[0] == disassemblies[1]
        sites_total += len(row['allocation_instructions'])
        reviewed.append(dict(path=row['path'],bytes=len(new),
                             sha256=hashlib.sha256(new).hexdigest(),
                             changed_bytes=len(changed),
                             allocation_sites=row['allocation_instructions']))
    assert len(reviewed) == 7 and sites_total == 14
    first = next(row for row in rows if row['path'] == 'odm/lib64/hw/camera.xiaomi.so')

    def reject(name, layout, source=Path(first['source'])):
        output = args.work / (name + '-rejected.so')
        command = ['python3', tool, '--layout', layout, '--input', source,
                   '--output', output, '--name', 'camera.xiaomi.so']
        result = subprocess.run(command, capture_output=True, text=True)
        (args.work / (name + '.log')).write_text(result.stdout + result.stderr)
        assert result.returncode != 0 and not output.exists(), name
        print('PASS rejected ' + name, flush=True)

    # Real AArch64 ELF archives exercise the size-symbol parser, independently
    # of the platform C++ static_asserts that reject an unknown header layout.
    for name, size, alignment in [('unknown-size', 1024, 8), ('wrong-alignment', 3376, 16)]:
        source = args.work / (name + '.c')
        source.write_text(f'char sheng_graphicbuffer_size[{size}];\n'
                          f'char sheng_graphicbuffer_alignment[{alignment}];\n')
        obj = args.work / (name + '.o')
        archive = args.work / (name + '.a')
        subprocess.run([CLANG / 'clang', '--target=aarch64-linux-android29', '-c', source,
                        '-o', obj], check=True)
        subprocess.run([CLANG / 'llvm-ar', 'rcD', archive, obj], check=True)
        reject(name, archive)
    truncated = args.work / 'truncated.a'
    truncated.write_bytes(args.layout.read_bytes()[:-17])
    reject('truncated-archive', truncated)
    empty = args.work / 'empty.a'
    empty.write_bytes(b'!<arch>\n')
    reject('missing-symbols', empty)
    wrong_source = args.work / 'changed-input.so'
    wrong_source.write_bytes(Path(first['source']).read_bytes() + b'changed')
    reject('unreviewed-input', args.layout, wrong_source)
    result = dict(reviewed_outputs=reviewed, allocation_sites=sites_total,
                  non_allocation_bytes_unchanged=True, constructors_unchanged=True,
                  malformed_input_checks_passed=5, runtime_verified=False,
                  factory_libgui_excluded_because_current_source_provider=True)
    (args.work / 'review-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Seven real libraries and fourteen allocations reviewed; five invalid inputs rejected.', flush=True)


if __name__ == '__main__':
    main()
