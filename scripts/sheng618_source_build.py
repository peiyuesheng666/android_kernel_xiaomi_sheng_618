#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Portable build entry point shipped as build_release.py in the source archive."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--prebuilts', type=Path, required=True, help='Google kernel prebuilts directory')
parser.add_argument('--elfutils', type=Path, required=True, help='elfutils >= 0.193 install prefix')
parser.add_argument('--stock-boot', type=Path, help='Read-only sheng OS3.0.303 boot.img template')
parser.add_argument('--jobs', type=int, default=os.cpu_count())
parser.add_argument('--out', type=Path, default=root / 'out')
parser.add_argument('--config-only', action='store_true', help='Check fresh kernel configuration without compiling')
args = parser.parse_args()
assert args.jobs > 0
k = root / 'k618'
ack, soc, tp = k / 'ws/common', k / 'soc', k / 'vendor/qcom/opensource'
output = args.out.resolve()
output.mkdir(parents=True, exist_ok=True)
clang = args.prebuilts.resolve() / 'clang/host/linux-x86/clang-r584948c/bin'
rust = args.prebuilts.resolve() / 'rust-toolchain/linux-x86/1.91.1.p3'
elf = args.elfutils.resolve()
assert (clang / 'clang').is_file() and (elf / 'include/elfutils/libdw.h').is_file()
env = {**os.environ, 'KBUILD_GENDWARFKSYMS_STABLE': '1', 'LOCALVERSION': '',
       'KBUILD_BUILD_USER': 'peiyuesheng', 'KBUILD_BUILD_HOST': 'MiFans', 'KBUILD_BUILD_VERSION': '1',
       'LIBCLANG_PATH': str(clang.parent / 'lib'), 'RUSTC_BOOTSTRAP': '1',
       'RUST_LIB_SRC': str(rust / 'lib/rustlib/src/rust/library'),
       'MAKEFLAGS': 'HOSTCFLAGS=-O2\\ -I' + str(elf / 'include') +
                    ' HOSTLDFLAGS=-L' + str(elf / 'lib') + '\\ -Wl,-rpath,' + str(elf / 'lib'),
       'PATH': ':'.join(map(str, [clang, rust / 'bin', args.prebuilts / 'clang-tools/linux-x86/bin',
                    args.prebuilts / 'kernel-build-tools/linux_musl-x86/bin',
                    args.prebuilts / 'build-tools/linux-x86/bin'])) + ':/usr/sbin:/usr/bin:/sbin:/bin'}
make = ['make', '-C', ack, 'O=' + str(output), 'ARCH=arm64', 'LLVM=1', 'LLVM_IAS=1',
        'PAHOLE=' + str(args.prebuilts / 'kernel-build-tools/linux_musl-x86/bin/pahole'),
        '-j' + str(args.jobs)]


def run(label, command):
    print(label, flush=True)
    with (output / (label + '.log')).open('w') as stream:
        result = subprocess.run(list(map(str, command)), env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print('\n'.join((output / (label + '.log')).read_text(errors='replace').splitlines()[-60:]))
        raise SystemExit(result.returncode)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


shutil.copyfile(root / 'configs/release.config', output / '.config')
subprocess.run([ack / 'scripts/config', '--file', output / '.config',
                '--set-str', 'INITRAMFS_SOURCE', '', '--disable', 'SHENG_BOOTLOG'], check=True)
run('kernel-config', [*make, 'olddefconfig'])
if args.config_only:
    config = (output / '.config').read_text()
    assert not any(line.endswith('=y') or line.endswith('=m') for line in config.splitlines()
                   if line.startswith(('CONFIG_KSU', 'CONFIG_SUSFS', 'CONFIG_SHENG_BOOTLOG')))
    print('Fresh source configuration passed; test logger and built-in root remain disabled.')
    raise SystemExit(0)
run('kernel', [*make, 'Image', 'modules'])
baseline_symbols = [line for line in (output / 'Module.symvers').read_text().splitlines()
                    if line.split('\t')[2] == 'vmlinux']
run('soc', [*make, 'M=' + str(soc), 'modules'])
symbols = [soc / 'Module.symvers']
legacy = k / 'vendor/xiaomi/adsprpc-515'
rpc_flags = ['SOC=' + str(soc), 'CONFIG_ARCH_KALAMA=y',
             'NOSTDINC_FLAGS=-nostdinc -I' + str(soc / 'include') + ' -I' + str(soc / 'include/uapi'),
             'KCFLAGS=-include ' + str(k / 'tp-autoconf.h')]
plan = json.loads((root / 'configs/techpacks.json').read_text())


def expand(value, stage):
    values = {'%M': plan['multimedia_includes'], '%R': plan['network_includes'],
              '%C': 'CONFIG_ARCH_CANOE=y', '%L': '-DCONFIG_RMNET_LA_PLATFORM=1',
              '%I': '-DCONFIG_IPA3=1', '%D': str(stage), '%P': str(stage.parent),
              '%T': str(tp), '%W': str(ack)}
    for old, new in values.items():
        value = value.replace(old, new)
    return value.replace('${NFC_TRACE:+-DK618_NFC_TRACE}', '')


for item in plan['modules']:
    name, directory, variables, incs, defs = item
    if name in ('video', 'eva'):
        continue
    stage = (tp / directory).resolve()
    extra_symbols = list(symbols)
    if name == 'eva515':
        run('rpc-before-eva', [*make, 'M=' + str(legacy), 'modules', *rpc_flags,
                              'KBUILD_EXTRA_SYMBOLS=' + str(soc / 'Module.symvers')])
        incs = str(legacy / 'include') + ' ' + incs
        defs += ' -DCONFIG_MSM_ADSPRPC=1'
        extra_symbols = [p for p in extra_symbols if p != tp / 'dsp-kernel/Module.symvers']
        extra_symbols.append(legacy / 'Module.symvers')
    run('tp-' + name, [*make, 'M=' + str(stage), 'modules', 'CONFIG_ARCH_KALAMA=y',
        'KERNEL_SRC=' + str(ack), 'KERNEL_ROOT=' + str(ack),
        'KBUILD_EXTRA_SYMBOLS=' + ' '.join(map(str, extra_symbols)),
        'NOSTDINC_FLAGS=-nostdinc -I' + str(soc / 'include') + ' -I' + str(soc / 'include/uapi') +
            ''.join(' -I' + path for path in expand(incs, stage).split()),
        'KCFLAGS=-Wno-error -include ' + str(k / 'tp-autoconf.h') + ' ' + expand(defs, stage),
        *shlex.split(expand(variables, stage))])
    symbols.append(stage / 'Module.symvers')
for group in ('pogo', 'cs35l43', 'touch', 'fingerprint', 'hall', 'keyboard', 'ps5169'):
    stage = k / 'sheng-ports' / group
    run('tablet-' + group, [*make, 'M=' + str(stage), 'modules', 'SOC=' + str(soc),
                           'KBUILD_EXTRA_SYMBOLS=' + ' '.join(map(str, symbols))])
    symbols.append(stage / 'Module.symvers')
run('loader', [*make, 'M=' + str(k / 'mark'), 'modules'])
layer = output / 'layer'
shutil.copytree(root / 'configs/module-layer', layer, dirs_exist_ok=True)
modules = layer / 'lib/modules'
module_map = json.loads((root / 'configs/module-sources.json').read_text())
assert len(module_map) == 344
for name, source in module_map.items():
    path = output / source[4:] if source.startswith('out/') else k / source
    assert path.is_file(), path
    shutil.copyfile(path, modules / name)
    subprocess.run([clang / 'llvm-strip', '--strip-debug', modules / name], check=True)
subprocess.run([clang / 'clang', '--target=aarch64-linux-gnu', '-O2', '-nostdlib', '-static',
                '-ffreestanding', '-fno-stack-protector', '-fuse-ld=lld', '-Wl,--build-id=none',
                '-s', '-o', layer / 'k618_umh', root / 'tools/k618_umh.c'], check=True, env=env)
release = (output / 'include/config/kernel.release').read_text().strip()
dep_root = output / 'depmod-root'
target = dep_root / 'lib/modules' / release
(target / 'kernel').mkdir(parents=True, exist_ok=True)
for module in modules.glob('*.ko'):
    shutil.copyfile(module, target / 'kernel' / module.name)
for name in ('modules.builtin', 'modules.builtin.modinfo'):
    shutil.copyfile(output / name, target / name)
(target / 'modules.order').write_text(''.join('kernel/' + name + '\n' for name in sorted(module_map)))
result = subprocess.run(['depmod', '-b', dep_root, '-F', output / 'System.map', '-e', release],
                        capture_output=True, text=True)
assert result.returncode == 0 and not result.stderr.strip(), result.stderr
for name in ('modules.dep', 'modules.alias', 'modules.softdep'):
    (modules / name).write_text((target / name).read_text().replace('kernel/', '/lib/modules/'))
overlay = output / 'overlay.cpio'
with overlay.open('wb') as stream:
    subprocess.run(['cpio', '--null', '-o', '-H', 'newc', '-R', '0:0', '--quiet'], check=True,
        input=('\0'.join(sorted(p.relative_to(layer).as_posix() for p in layer.rglob('*'))) + '\0').encode(),
        cwd=layer, stdout=stream)
subprocess.run([ack / 'scripts/config', '--file', output / '.config',
                '--set-str', 'INITRAMFS_SOURCE', overlay, '--disable', 'INITRAMFS_FORCE'], check=True)
run('embedded-config', [*make, 'olddefconfig'])
run('embedded-image', [*make, 'Image'])
assert sorted(baseline_symbols) == sorted((output / 'vmlinux.symvers').read_text().splitlines())
image = output / 'arch/arm64/boot/Image'
shutil.copyfile(image, output / 'Image')
if args.stock_boot:
    stock = args.stock_boot.resolve()
    assert sha(stock) == '4156a2369f78bc5df61b6a521b07a508dedf20d5e63c207d30986ae37df3eaea'
    unpack = root / 'tools/mkbootimg/unpack_bootimg.py'
    command = shlex.split(subprocess.check_output([sys.executable, unpack, '--boot_img', stock,
        '--out', output / 'stock-parts', '--format=mkbootimg'], text=True))
    assert (output / 'stock-parts/ramdisk').read_bytes() == b''
    compressed = output / 'Image.gz'
    compressed.write_bytes(gzip.compress(image.read_bytes(), compresslevel=9, mtime=0))
    command[command.index('--kernel') + 1] = str(compressed)
    command[command.index('--cmdline') + 1] = 'loglevel=4'
    subprocess.run([sys.executable, root / 'tools/mkbootimg/mkbootimg.py', *command,
                    '--output', output / 'boot.img'], check=True)
    avb = root / 'tools/avbtool.py'
    subprocess.run([sys.executable, avb, 'add_hash_footer', '--image', output / 'boot.img',
        '--partition_name', 'boot', '--partition_size', str(stock.stat().st_size()), '--algorithm', 'NONE'], check=True)
    subprocess.run([sys.executable, avb, 'verify_image', '--image', output / 'boot.img'], check=True)
print('Built ' + str(output / 'Image') + '; no device partitions were written.')
