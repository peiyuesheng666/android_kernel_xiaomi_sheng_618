#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build r60's display clock takeover candidate from the verified r56 layer."""
import os
import subprocess
import sys
from build_sheng618_upstream import ACK, K618, OUT, PROJECT, ROOT, environment

subprocess.run([sys.executable, PROJECT / 'scripts/prepare_sheng618_dispcc_live.py'], check=True)
stage = K618 / 'soc'
log = ROOT / 'logs/hardware-r60-soc-build.log'
with log.open('w') as stream:
    result = subprocess.run(['make', '-C', str(ACK), 'O=' + str(OUT),
        'ARCH=arm64', 'LLVM=1', 'LLVM_IAS=1', '-j' + str(os.cpu_count()),
        'M=' + str(stage), 'modules'], env=environment(os.cpu_count()),
        stdout=stream, stderr=subprocess.STDOUT)
if result.returncode:
    print('\n'.join(log.read_text(errors='replace').splitlines()[-45:]))
    raise SystemExit(result.returncode)
subprocess.run([sys.executable, PROJECT / 'scripts/build_sheng618_layer_variant.py',
    '--tag', 'hardware-r60', '--base', 'hardware-r56',
    '--replace', 'dispcc-kalama.ko=' + str(stage / 'dispcc-kalama.ko'),
    '--pre-driver-hold-ms', '8000'], check=True)
