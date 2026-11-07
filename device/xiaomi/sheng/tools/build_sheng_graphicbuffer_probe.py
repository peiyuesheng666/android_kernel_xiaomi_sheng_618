#!/usr/bin/env python3
"""Build an isolated libui object-storage probe with actual vendor compile flags."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
WORK = Path('/root/sheng-lineage/hardware-diagnostics/graphicbuffer-abi-r25')


def commands(target):
    return subprocess.check_output([
        ROM / 'prebuilts/build-tools/linux-x86/bin/ninja', '-f',
        'out/combined-lineage_sheng.ninja', '-t', 'commands', target], cwd=ROM,
        text=True).splitlines()


def main():
    assert DEVICE == ROM / 'device/xiaomi/sheng'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=WORK)
    work = parser.parse_args().work
    work.mkdir(parents=True, exist_ok=False)
    ui = commands('out/target/product/sheng/vendor/lib64/libui.so')
    compile_lines = [line for line in ui if line.endswith(' frameworks/native/libs/ui/GraphicBuffer.cpp')
                     and '/android_vendor_arm64_' in line]
    assert len(compile_lines) == 1
    compile_args = shlex.split(compile_lines[0])
    compile_args = compile_args[next(i for i, arg in enumerate(compile_args) if arg.endswith('/clang++')):]
    compile_args[compile_args.index('-o') + 1] = str(work / 'probe.o')
    compile_args[compile_args.index('-MF') + 1] = str(work / 'probe.d')
    compile_args[-1] = str(DEVICE / 'tools/ShengGraphicBufferAbiProbe.cpp')
    service = commands('out/target/product/sheng/vendor/bin/hw/dolbycodec2')
    links = [line for line in service if 'clang++ ' in line and '/sheng-dolbycodec2/' in line
             and ' -c ' not in line]
    assert len(links) == 1
    link_args = shlex.split(links[0])
    response = [arg for arg in link_args if arg.startswith('@')]
    assert len(response) == 1
    service_inputs = shlex.split((ROM / response[0][1:]).read_text())
    runtime_names = {'libc.so', 'libc++.so', 'libdl.so', 'libm.so', 'libutils.so', 'liblog.so'}
    runtime = [arg for arg in service_inputs if Path(arg).name in runtime_names]
    assert {Path(arg).name for arg in runtime} == runtime_names
    builtins = [arg for arg in service_inputs if Path(arg).name == 'libclang_rt.builtins-aarch64-android.a']
    assert len(builtins) == 1
    sanitizer = (ROM / builtins[0]).parent / 'libclang_rt.ubsan_minimal-aarch64-android.a'
    assert sanitizer.is_file()
    ui_libraries = list((ROM / 'out/soong/.intermediates/frameworks/native/libs/ui/libui').glob(
        'android_vendor_arm64*_shared/libui.so'))
    assert len(ui_libraries) == 1
    inputs = [str(work / 'probe.o'), *builtins, str(sanitizer), *runtime, str(ui_libraries[0])]
    rsp = work / 'probe.rsp'
    rsp.write_text(shlex.join(inputs) + '\n')
    link_args[link_args.index(response[0])] = '@' + str(rsp)
    link_args[link_args.index('-o') + 1] = str(work / 'sheng-graphicbuffer-abi-probe')
    (work / 'commands.json').write_text(json.dumps([compile_args, link_args], indent=2) + '\n')
    subprocess.run(compile_args, cwd=ROM, check=True)
    subprocess.run(link_args, cwd=ROM, check=True)
    print(link_args[link_args.index('-o') + 1])


if __name__ == '__main__':
    main()
