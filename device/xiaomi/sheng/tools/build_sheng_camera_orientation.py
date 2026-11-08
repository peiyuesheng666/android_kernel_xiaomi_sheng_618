#!/usr/bin/env python3
"""Compile the board adapter/probe with cached, audited vendor compile/link flags.

This small compile avoids regenerating the complete Soong graph on this host.
Android.bp remains the normal product integration. No platform source is edited.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
TEMPLATE = Path('/root/sheng-lineage/hardware-diagnostics/graphicbuffer-abi-r25/commands.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    work = parser.parse_args().work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    compile_base, link_base = json.loads(TEMPLATE.read_text())
    assert compile_base[0] == link_base[0] == 'prebuilts/clang/host/linux-x86/clang-r596125/bin/clang++'
    assert '-D__ANDROID_VENDOR_API__=202604' in compile_base
    response = [item for item in link_base if item.startswith('@')]
    assert len(response) == 1
    inputs = shlex.split(Path(response[0][1:]).read_text())
    names = {'libc.so', 'libm.so', 'libdl.so', 'libc++.so', 'liblog.so',
             'libclang_rt.builtins-aarch64-android.a', 'libclang_rt.ubsan_minimal-aarch64-android.a'}
    libraries = [item for item in inputs if Path(item).name in names]
    assert {Path(item).name for item in libraries} == names
    metadata = ROM / 'out/soong/.intermediates/system/media/camera/libcamera_metadata/android_vendor_arm64_armv8-2a-dotprod_kryo_shared/libcamera_metadata.so'
    assert metadata.is_file()
    commands = []
    for source, name, shared in [('CameraModule.cpp', 'camera.sheng.so', True),
                                  ('CameraModuleTest.cpp', 'sheng-camera-orientation-test', False)]:
        compile_args = list(compile_base)
        old_source = [item for item in compile_args if item.endswith('.cpp')]
        assert len(old_source) == 1
        compile_args[compile_args.index(old_source[0])] = str(DEVICE / 'interfaces/compat/camera' / source)
        obj = work / (name + '.o')
        compile_args[compile_args.index('-o') + 1] = str(obj)
        compile_args[compile_args.index('-MF') + 1] = str(work / (name + '.d'))
        compile_args += ['-Ihardware/libhardware/include_all', '-Isystem/media/camera/include', '-Werror', '-fno-lto']
        rsp = work / (name + '.rsp')
        rsp.write_text(shlex.join([str(obj), *libraries, str(metadata)]) + '\n')
        link_args = [('@' + str(rsp)) if item == response[0] else item for item in link_base]
        link_args[link_args.index('-o') + 1] = str(work / name)
        if shared:
            link_args = [item.replace('/crtbegin_dynamic/', '/crtbegin_so/').replace('/crtbegin_dynamic.o', '/crtbegin_so.o')
                         .replace('/crtend_android/', '/crtend_so/').replace('/crtend_android.o', '/crtend_so.o')
                         for item in link_args if item != '-pie' and not item.startswith('-Wl,-dynamic-linker,')]
            link_args += ['-shared', '-Wl,-soname,camera.sheng.so']
        commands.extend([compile_args, link_args])
        subprocess.run(compile_args, cwd=ROM, check=True)
        subprocess.run(link_args, cwd=ROM, check=True)
    (work / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    print(work)


if __name__ == '__main__':
    main()
