#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Incrementally build explicitly selected SOC modules without replaying recipes."""
import argparse
import os
import re
import subprocess
import sys
from build_sheng618_upstream import ACK, K618, OUT, PROJECT, ROOT, environment

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', required=True)
parser.add_argument('--base', required=True)
parser.add_argument('--module', action='append', required=True)
parser.add_argument('--smmu-scan-watch-ms', type=int, default=0, choices=[0, 3000])
args = parser.parse_args()
modules = [value.split('=', 1) for value in args.module]
modules = [(names[0], names[-1]) for names in modules]
assert all(re.fullmatch(r'[A-Za-z0-9_-]+\.ko', name)
           for names in modules for name in names)
assert len({name for name, source in modules}) == len(modules)
base_modules = ROOT / 'diagnostic' / args.base / 'layer/lib/modules'
assert all((base_modules / name).is_file() for name, source in modules)
stage = K618 / 'soc'
jobs = os.cpu_count()
log = ROOT / 'logs' / (args.tag + '-soc-build.log')
print('Building selected SOC module changes: ' + ', '.join(args.module), flush=True)
with log.open('w') as stream:
    result = subprocess.run(['make', '-C', str(ACK), 'O=' + str(OUT), 'ARCH=arm64',
        'LLVM=1', 'LLVM_IAS=1', '-j' + str(jobs), 'M=' + str(stage), 'modules'],
        env=environment(jobs), stdout=stream, stderr=subprocess.STDOUT)
if result.returncode:
    print('\n'.join(log.read_text(errors='replace').splitlines()[-50:]), flush=True)
    raise SystemExit(result.returncode)
assert all((stage / source).is_file() for name, source in modules)
subprocess.run([sys.executable, PROJECT / 'scripts/build_sheng618_layer_variant.py',
    '--tag', args.tag, '--base', args.base,
    '--smmu-scan-watch-ms', str(args.smmu_scan_watch_ms),
    *[arg for name, source in modules for arg in ('--replace', name + '=' + str(stage / source))]],
    check=True)
