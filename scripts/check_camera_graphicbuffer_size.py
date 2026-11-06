#!/usr/bin/env python3
"""Measure GraphicBuffer ABI using the exact vendor libui compilation flags."""
from pathlib import Path
import os
import shlex
import subprocess

rom = Path('/root/sheng-lineage/lineage-24.0')
workspace = Path(__file__).resolve().parents[1]
ninja = rom / 'prebuilts/build-tools/linux-x86/bin/ninja'
commands = subprocess.check_output([
    str(ninja), '-f', 'out/combined-lineage_sheng.ninja', '-t', 'commands',
    'out/target/product/sheng/vendor/lib64/libui.so',
], cwd=rom, text=True).splitlines()
candidates = [line for line in commands if line.endswith(' frameworks/native/libs/ui/GraphicBuffer.cpp')
              and '/android_vendor_arm64_' in line]
assert len(candidates) == 1, [line[-300:] for line in commands if 'GraphicBuffer.cpp' in line]
args = shlex.split(candidates[0])
compiler = next(i for i, word in enumerate(args) if word.endswith('/clang++'))
args = args[compiler:]
source = Path('/root/sheng-lineage/system-bringup-r2/graphicbuffer-size-check.cpp')
source.write_text('#include <ui/GraphicBuffer.h>\n'
                  'static_assert(sizeof(android::GraphicBuffer) == 256, "OEM allocation is 256 bytes");\n')
args[args.index('frameworks/native/libs/ui/GraphicBuffer.cpp')] = str(source)
for option in ('-o', '-MF'):
    if option in args:
        index = args.index(option)
        del args[index:index + 2]
args = [word for word in args if word not in ('-c', '-MD')]
args.append('-fsyntax-only')
environment = dict(os.environ)
environment['PWD'] = str(rom)
result = subprocess.run(args, cwd=rom, env=environment, capture_output=True, text=True)
report = result.stdout + result.stderr
(workspace / 'reports/device/system-bringup-r2-followup-20261106/graphicbuffer-size-check.txt').write_text(report)
print(report[-4000:])
