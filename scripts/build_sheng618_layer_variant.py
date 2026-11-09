#!/usr/bin/env python3
"""Build controlled module changes without reports or source recipe replay."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from audit_kernel618_modules import ElfModule, check_candidate
from audit_sheng618_overlay import entries
from build_sheng618_upstream import CLANG, OUT, PROJECT, ROOT

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', required=True)
parser.add_argument('--base', required=True)
parser.add_argument('--release', action='store_true')
parser.add_argument('--pre-driver-hold-ms', type=int, default=0, choices=[0, 8000])
parser.add_argument('--post-dispcc-hold-ms', type=int, default=0, choices=[0, 8000])
parser.add_argument('--before-display-hold-ms', type=int, default=0, choices=[0, 8000])
parser.add_argument('--smmu-scan-watch-ms', type=int, default=0, choices=[0, 3000])
parser.add_argument('--omit', action='append', default=[])
parser.add_argument('--replace', action='append', default=[], metavar='MODULE=PATH')
parser.add_argument('--prioritize-before', action='append', default=[], metavar='MODULE=ANCHOR',
                    help='Move a module and its later prerequisites before an anchor')
args = parser.parse_args()
assert args.omit or args.replace or args.prioritize_before, 'Specify a module or load-order change'
replacements = {}
for value in args.replace:
    name, path = value.split('=', 1)
    assert re.fullmatch(r'[A-Za-z0-9_-]+\.ko', name), name
    assert name not in replacements and name not in args.omit
    replacements[name] = Path(path)
    assert replacements[name].is_file()
for tag in (args.tag, args.base):
    assert re.fullmatch(r'(?:hardware|release)-r[0-9]+', tag), tag
for name in args.omit:
    assert re.fullmatch(r'[A-Za-z0-9_-]+\.ko', name), name
assert len(args.omit) == len(set(args.omit))
base = ROOT / 'diagnostic' / args.base
native = ROOT / 'diagnostic' / args.tag
assert base.is_dir() and not native.exists(), 'Preserve existing candidates'
layer = native / 'layer'
shutil.copytree(base / 'layer', layer)
modules = layer / 'lib/modules'
for name in args.omit:
    assert (modules / name).is_file(), name
    (modules / name).unlink()
for name, path in replacements.items():
    assert (modules / name).is_file(), 'Replacement must already exist in base: ' + name
    shutil.copyfile(path, modules / name)
    subprocess.run([CLANG / 'llvm-strip', '--strip-debug', modules / name], check=True)
batch = modules / 'k618_batch.load'
lines = batch.read_text().splitlines(keepends=True)
removed = [line for line in lines if Path(line.strip()).name in args.omit]
assert len(removed) == len(args.omit), removed
batch.write_text(''.join(line for line in lines if line not in removed))
if args.prioritize_before:
    dependencies = {}
    for line in (modules / 'modules.dep').read_text().splitlines():
        name, deps = line.split(':', 1)
        dependencies[Path(name).name] = {Path(value).name for value in deps.split()}
    order = batch.read_text().splitlines()
    assert len(order) == len(set(order)), 'Duplicate batch entries'
    original_order = list(order)
    for spec in args.prioritize_before:
        target_name, anchor_name = spec.split('=', 1)
        assert all(re.fullmatch(r'[A-Za-z0-9_-]+\.ko', name)
                   for name in (target_name, anchor_name)), spec
        assert target_name in order and anchor_name in order
        closure, pending = set(), [target_name]
        while pending:
            name = pending.pop()
            if name in closure:
                continue
            assert name in dependencies, 'Missing dependency metadata: ' + name
            closure.add(name)
            pending.extend(dependencies[name] - closure)
        assert anchor_name not in closure, 'Anchor is required by the target'
        anchor_index = order.index(anchor_name)
        moved = [name for i, name in enumerate(order)
                 if i >= anchor_index and name in closure]
        order = [name for name in order if name not in moved]
        anchor_index = order.index(anchor_name)
        order[anchor_index:anchor_index] = moved
        positions = {name: i for i, name in enumerate(order)}
        for name in closure & positions.keys():
            for dep in dependencies[name] & positions.keys():
                assert positions[dep] < positions[name], (name, dep)
        assert positions[target_name] < positions[anchor_name]
        print('Prioritized before ' + anchor_name + ': ' + ', '.join(moved), flush=True)
    assert len(order) == len(original_order) and set(order) == set(original_order)
    batch.write_text(''.join(name + '\n' for name in order))
checked = check_candidate({p.name: ElfModule(p) for p in modules.glob('*.ko')},
    {'source_keep_modules': ['zram.ko', 'zsmalloc.ko']}, OUT,
    [modules / 'zram.ko', modules / 'zsmalloc.ko'], '6.18')
assert checked['abi_passed'], checked['issue_counts']
release = (OUT / 'include/config/kernel.release').read_text().strip()
dep_root = native / 'depmod-root'
target = dep_root / 'lib/modules' / release
kernel = target / 'kernel'
kernel.mkdir(parents=True)
for module in modules.glob('*.ko'):
    os.link(module, kernel / module.name)
for name in ('modules.builtin', 'modules.builtin.modinfo'):
    shutil.copyfile(OUT / name, target / name)
(target / 'modules.order').write_text(''.join('kernel/' + name + '\n'
    for name in sorted(p.name for p in modules.glob('*.ko'))))
result = subprocess.run(['depmod', '-b', dep_root, '-F', OUT / 'System.map', '-e', release],
    capture_output=True, text=True)
assert result.returncode == 0 and not result.stderr.strip(), result.stderr
for name in ('modules.dep', 'modules.alias', 'modules.softdep'):
    (modules / name).write_text((target / name).read_text().replace('kernel/', '/lib/modules/'))
overlay = native / 'overlay.cpio'
names = sorted(p.relative_to(layer).as_posix() for p in layer.rglob('*'))
with overlay.open('wb') as stream:
    subprocess.run(['cpio', '--null', '-o', '-H', 'newc', '-R', '0:0', '--quiet'],
        input=('\0'.join(names) + '\0').encode(), cwd=layer, stdout=stream, check=True)
before = {n: (m, d) for n, m, d in entries((base / 'overlay.cpio').read_bytes())}
after = {n: (m, d) for n, m, d in entries(overlay.read_bytes())}
assert before.keys() - after.keys() == {'lib/modules/' + n for n in args.omit}
assert not after.keys() - before.keys()
changed = {n for n in after if before[n] != after[n]}
allowed = {'lib/modules/' + n for n in ('modules.dep', 'modules.alias', 'modules.softdep', 'k618_batch.load')}
allowed |= {'lib/modules/' + n for n in replacements}
assert changed <= allowed, changed
print('Verified module changes: ' + ', '.join([*args.omit, *replacements]) + '; other binaries preserved', flush=True)
subprocess.run([sys.executable, PROJECT / 'scripts/build_sheng618_disklog_boot.py',
    '--tag', args.tag, '--overlay', overlay, '--legacy-module-reuse', '--legacy-fscrypt',
    '--legacy-firmware-lsm', '--pre-driver-hold-ms', str(args.pre_driver_hold_ms),
    '--post-dispcc-hold-ms', str(args.post_dispcc_hold_ms),
    '--before-display-hold-ms', str(args.before_display_hold_ms),
    '--smmu-scan-watch-ms', str(args.smmu_scan_watch_ms),
    '--no-records', *(['--release'] if args.release else [])], check=True)
