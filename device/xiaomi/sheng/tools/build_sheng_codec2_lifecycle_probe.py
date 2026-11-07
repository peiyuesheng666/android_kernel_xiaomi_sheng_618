#!/usr/bin/env python3
"""Compile a device-owned standalone lifecycle probe using reviewed service flags."""
import json
from pathlib import Path
import shlex
import subprocess

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
WORK = Path('/root/sheng-lineage/hardware-diagnostics/codec2-lifecycle-r24')


def main():
    assert DEVICE == ROM / 'device/xiaomi/sheng'
    candidates = list((ROM / 'out/soong/.intermediates/device/xiaomi/sheng/interfaces/compat/'
                       'codec2/sheng-dolbycodec2').glob('android_vendor_*/dolbycodec2'))
    assert len(candidates) == 1, candidates
    commands = subprocess.check_output([
        ROM / 'prebuilts/build-tools/linux-x86/bin/ninja', '-f',
        'out/combined-lineage_sheng.ninja', '-t', 'commands',
        candidates[0].relative_to(ROM)], cwd=ROM, text=True).splitlines()
    compile_lines = [line for line in commands if line.endswith(
        ' device/xiaomi/sheng/interfaces/compat/codec2/service.cpp')]
    link_lines = [line for line in commands if 'clang++ ' in line
                  and '/sheng-dolbycodec2/' in line and ' -c ' not in line]
    assert len(compile_lines) == len(link_lines) == 1
    WORK.mkdir(parents=True, exist_ok=True)
    compile_args = shlex.split(compile_lines[0])
    assert compile_args.pop(0) == 'PWD=/proc/self/cwd'
    original_object = compile_args[compile_args.index('-o') + 1]
    compile_args[compile_args.index('-o') + 1] = str(WORK / 'probe.o')
    compile_args[compile_args.index('-MF') + 1] = str(WORK / 'probe.d')
    compile_args[-1] = str(DEVICE / 'tools/ShengCodec2LifecycleProbe.cpp')
    link_args = shlex.split(link_lines[0])
    responses = [arg for arg in link_args if arg.startswith('@')]
    assert len(responses) == 1
    response_args = shlex.split((ROM / responses[0][1:]).read_text())
    assert response_args.count(original_object) == 1
    response_args[response_args.index(original_object)] = str(WORK / 'probe.o')
    response = WORK / 'probe.rsp'
    response.write_text(shlex.join(response_args) + '\n')
    link_args[link_args.index(responses[0])] = '@' + str(response)
    link_args[link_args.index('-o') + 1] = str(WORK / 'sheng-codec2-lifecycle-probe-r24')
    (WORK / 'commands.json').write_text(json.dumps([compile_args, link_args], indent=2) + '\n')
    subprocess.run(compile_args, cwd=ROM, check=True)
    subprocess.run(link_args, cwd=ROM, check=True)
    print(link_args[link_args.index('-o') + 1])


if __name__ == '__main__':
    main()
