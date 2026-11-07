#!/usr/bin/env python3
"""Route only stock Dolby video foundation imports to the legacy AHandler ABI.

No text instructions, sizes, vtables, C2 interfaces or platform libraries change.
The patched foundation is the same verified private copy used by DAP. Modern
SimpleC2Component/WorkHandler keep their ordinary foundation dependency.
"""
import argparse
import hashlib
import json
from pathlib import Path

from sheng_elf_compat import Elf

DEVICE = Path(__file__).resolve().parents[1]
ROM = Path('/root/sheng-lineage/lineage-24.0')
STOCK = Path('/root/sheng-lineage/firmware-dump/partitions/vendor/lib64')
INPUTS = {
    'c2.dolby.hevc.dec.so': '801cbdfeac13711241193185f5d7a057582c4da9813245cd562dc7e10798312f',
    'c2.dolby.hevc.sec.dec.so': '37f3a3b5751c643b82f7dd60871f3ad44afa4084533451c3a40028b2e3bd9a9d',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'Never overwrite candidate or release outputs'
    foundation = ROM / 'out/target/product/sheng/vendor/lib64/libstagefright_foundation.so'
    assert sha(foundation) == 'f72c9caa7deb28268aaad92cab14cfea8f4addf3f42c7ff501904b267d724ed3'
    private = DEVICE / 'interfaces/compat/dolby/libshgdolby_foundation.so'
    assert sha(private) == '97a7b4b29feb486a2f2cfd62ea289563129fee2a6be8ab9b6750a3f0ba2ea3c9'
    original = Elf(foundation)
    rename = {old: old.replace('7android', '7shgdap_') for _, index, old in original.symbols
              if index and '7android' in old}
    exported = {old for _, index, old in Elf(private).symbols if index}
    assert set(rename.values()) <= exported
    args.output.mkdir(parents=True)
    files = []
    for name, expected in INPUTS.items():
        source = STOCK / name
        assert sha(source) == expected, name
        client = Elf(source)
        count = sum(old in rename for _, _, old in client.symbols)
        assert count > 0, name
        # The new mutex at +96 overlaps the stock handler's first subclass
        # member; route its messages without touching the modern WorkHandler.
        client.isolate(rename, 'libshgdolby_foundation.so')
        target = args.output / name
        client.write(target)
        # Symbol routing must never change executable code or static data.
        patched = Elf(target)
        for section_name, section in client.sections.items():
            if section_name in ('.dynstr', '.gnu.hash') or section[1] == 8:
                continue
            start, size = section[4:6]
            assert patched.data[start:start + size] == source.read_bytes()[start:start + size], section_name
        files.append(dict(name=name, original_sha256=expected, sha256=sha(target),
                          bytes=target.stat().st_size, renamed_symbols=count))
    report = dict(files=files, foundation_sha256=sha(private),
                  executable_sections_unchanged=True, runtime_verified=False)
    (args.output / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
