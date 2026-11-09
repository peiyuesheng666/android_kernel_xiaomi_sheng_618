#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build r60's display clock takeover candidate from the verified r56 layer."""
import os
import argparse
import subprocess
import sys
from build_sheng618_upstream import ACK, K618, OUT, PROJECT, ROOT, environment

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', default='hardware-r60')
parser.add_argument('--base', default='hardware-r56')
parser.add_argument('--pre-driver-hold-ms', type=int, default=8000, choices=[0, 8000])
parser.add_argument('--post-dispcc-hold-ms', type=int, default=0, choices=[0, 8000])
args = parser.parse_args()
subprocess.run([sys.executable, PROJECT / 'scripts/prepare_sheng618_dispcc_live.py'], check=True)
if args.post_dispcc_hold_ms:
    subprocess.run([sys.executable, PROJECT / 'scripts/prepare_sheng618_dispcc_posthold.py'], check=True)
stage = K618 / 'soc'
log = ROOT / 'logs' / (args.tag + '-soc-build.log')
with log.open('w') as stream:
    result = subprocess.run(['make', '-C', str(ACK), 'O=' + str(OUT),
        'ARCH=arm64', 'LLVM=1', 'LLVM_IAS=1', '-j' + str(os.cpu_count()),
        'M=' + str(stage), 'modules'], env=environment(os.cpu_count()),
        stdout=stream, stderr=subprocess.STDOUT)
if result.returncode:
    print('\n'.join(log.read_text(errors='replace').splitlines()[-45:]))
    raise SystemExit(result.returncode)
subprocess.run([sys.executable, PROJECT / 'scripts/build_sheng618_layer_variant.py',
    '--tag', args.tag, '--base', args.base,
    '--replace', 'dispcc-kalama.ko=' + str(stage / 'dispcc-kalama.ko'),
    '--pre-driver-hold-ms', str(args.pre_driver_hold_ms),
    '--post-dispcc-hold-ms', str(args.post_dispcc_hold_ms)], check=True)
