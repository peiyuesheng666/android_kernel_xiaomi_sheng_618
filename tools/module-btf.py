#!/usr/bin/env python3
"""Distill BTF in module copies and verify against the final embedded kernel."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile


def sections(path):
    with path.open('rb') as f:
        header = f.read(64)
        assert header[:6] == b'\x7fELF\x02\x01', path
        offset = struct.unpack_from('<Q', header, 40)[0]
        size, count, strings = struct.unpack_from('<HHH', header, 58)
        assert size == 64 and count > 0
        f.seek(offset)
        headers = [struct.unpack('<IIQQQQIIQQ', f.read(size)) for _ in range(count)]
        f.seek(headers[strings][4])
        names = f.read(headers[strings][5])
        result = {}
        for h in headers:
            name = names[h[0]:].split(b'\0', 1)[0].decode()
            if name in ('.BTF', '.BTF.base'):
                assert h[1] == 1 and h[5] > 0, (path, name)
                f.seek(h[4])
                data = f.read(h[5])
                assert len(data) == h[5] and data[:2] == b'\x9f\xeb'
                result[name] = data
        return result


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


p = argparse.ArgumentParser()
p.add_argument('action', choices=['extract', 'distill', 'verify'])
p.add_argument('--kernel', required=True, type=Path)
p.add_argument('--output', required=True, type=Path)
p.add_argument('--modules', type=Path)
p.add_argument('--tool', type=Path)
p.add_argument('--objcopy', type=Path)
p.add_argument('--count', type=int, default=348)
args = p.parse_args()
if args.action == 'extract':
    args.output.write_bytes(sections(args.kernel)['.BTF'])
    print(json.dumps(dict(bytes=args.output.stat().st_size, sha256=sha(args.output))))
    raise SystemExit(0)

modules = sorted(args.modules.glob('*.ko'))
assert len(modules) == args.count, len(modules)
records = []
with tempfile.TemporaryDirectory(prefix='sheng-btf-', dir=args.modules.parent) as tmp:
    tmp = Path(tmp)
    for module in modules:
        before = sections(module)
        if args.action == 'distill':
            assert set(before) == {'.BTF'}, module
            split, base, copy = tmp / 'split.btf', tmp / 'base.btf', tmp / 'module.ko'
            result = subprocess.run([args.tool, 'distill', args.kernel, module, split, base],
                                    check=True, capture_output=True, text=True)
            types = json.loads(result.stdout)
            assert types['distilled_base_types'] > 1, module
            subprocess.run([args.objcopy, '--update-section', '.BTF=' + str(split),
                            '--add-section', '.BTF.base=' + str(base),
                            '--set-section-flags', '.BTF.base=alloc,readonly', module, copy],
                           check=True, capture_output=True)
            converted = sections(copy)
            assert converted['.BTF'] == split.read_bytes()
            assert converted['.BTF.base'] == base.read_bytes()
            # Relocation must also succeed against the original base before committing.
            subprocess.run([args.tool, 'verify', args.kernel, copy], check=True, capture_output=True)
            copy.replace(module)
        else:
            assert set(before) == {'.BTF', '.BTF.base'}, module
            result = subprocess.run([args.tool, 'verify', args.kernel, module],
                                    check=True, capture_output=True, text=True)
            types = json.loads(result.stdout)
        records.append(dict(module=module.name, sha256=sha(module), types=types,
                            btf={name: dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
                                 for name, data in sections(module).items()}))
        if len(records) % 50 == 0:
            print(f'{args.action}: {len(records)}/{len(modules)}', flush=True)
report = dict(action=args.action, kernel_btf_sha256=sha(args.kernel),
              tool_sha256=sha(args.tool), module_count=len(records), modules=records,
              all_modules_passed=True)
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'modules'}))
