#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Export the exact prepared release sources without output trees or build caches."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
from build_sheng618_upstream import ACK, K618, PROJECT, ROOT, UPSTREAM

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', default='release-r70')
parser.add_argument('--resume-incomplete', action='store_true')
parser.add_argument('--replace-unpublished', action='store_true')
args = parser.parse_args()
assert re.fullmatch(r'release-r[0-9]+', args.revision)
dest = PROJECT / ('artifacts/sheng-6.18-' + args.revision)
build = json.loads((dest / 'build-result.json').read_text())
assert build['build_type'] == 'release'
hardware = json.loads((PROJECT / ('reports/kernel618-' + args.revision + '-hardware.json')).read_text())
assert hardware['android_boot_completed'], 'Test actual Android boot before exporting release sources'
native = ROOT / 'diagnostic' / args.revision
archive_name = 'sheng-6.18.32-' + args.revision + '-source.tar.gz'
if args.replace_unpublished:
    for path in (dest / archive_name, dest / 'source-package.json'):
        assert path.resolve().parent == dest.resolve() and not path.is_symlink()
        path.unlink(missing_ok=True)
    sums = dest / 'SHA256SUMS'
    sums.write_text(''.join(line + '\n' for line in sums.read_text().splitlines()
                            if not line.endswith('  ' + archive_name)))
export_parent = native / 'source-export'
stage = export_parent / ('sheng-6.18.32-' + args.revision + '-source')
if stage.exists():
    assert args.resume_incomplete and not (dest / 'source-package.json').exists()
    assert stage.resolve().is_relative_to(native.resolve()) and not stage.is_symlink()
    shutil.rmtree(stage)
stage.mkdir(parents=True)
excludes = ['.git', '.repo', '__pycache__', '.cache', '.tmp_versions', '.config', '.config.old',
            '*.o', '*.ko', '*.mod', '*.mod.c', '.*.cmd', '.*.d', 'Module.symvers', 'modules.order',
            '*.log', '*.log.*', 'vmlinux', 'System.map', '*.dtb', '*.dtbo', '*.cpio', '*.img', '*.pyc',
            'kernelsu', 'KernelSU', 'susfs4ksu', '.k618_susfs', 'susfs.c', 'susfs.h', 'susfs_def.h']
for relative in ('ws/common', 'soc', 'vendor', 'sheng-ports', 'mark'):
    source = K618 / relative
    target = stage / 'k618' / relative
    target.mkdir(parents=True)
    subprocess.run(['rsync', '-a', *['--exclude=' + value for value in excludes],
                    str(source) + '/', str(target) + '/'], check=True)
ps = stage / 'k618/sheng-ports/ps5169'
ps.mkdir()
subprocess.run(['rsync', '-a', *['--exclude=' + value for value in excludes],
                str(ROOT / 'ports/ps5169') + '/', str(ps) + '/'], check=True)
shutil.copyfile(K618 / 'tp-autoconf.h', stage / 'k618/tp-autoconf.h')
# Remove the now-unused build references along with the unenabled root sources.
for relative, line in (
        ('drivers/Kconfig', 'source "drivers/kernelsu/Kconfig"\n'),
        ('drivers/Makefile', 'obj-$(CONFIG_KSU) += kernelsu/\n'),
        ('fs/Makefile', 'obj-$(CONFIG_KSU_SUSFS) += susfs.o\n')):
    path = stage / 'k618/ws/common' / relative
    path.write_text(path.read_text().replace(line, ''))
shutil.copyfile(PROJECT / 'scripts/sheng618_source_build.py', stage / 'build_release.py')
configs = stage / 'configs'
configs.mkdir()
text = (dest / 'kernel.config').read_text()
text = re.sub(r'^CONFIG_INITRAMFS_SOURCE=.*$', 'CONFIG_INITRAMFS_SOURCE=""', text, flags=re.M)
(configs / 'release.config').write_text(text)
module_layer = configs / 'module-layer'
modules = module_layer / 'lib/modules'
modules.mkdir(parents=True)
for path in (native / 'layer/lib/modules').iterdir():
    if path.is_file() and path.suffix != '.ko':
        shutil.copyfile(path, modules / path.name)
old_map = json.loads((ROOT / 'diagnostic/hardware-r38/all-modules.json').read_text())['modules']
current_names = {p.name for p in (native / 'layer/lib/modules').glob('*.ko')}
module_map = {}
for name in sorted(current_names):
    old_name = name if name in old_map else 'qca_cld3_kiwi_v2.ko' if name == 'kiwi_v2.ko' else name
    path = Path(old_map[old_name]['source'])
    if path.is_relative_to(K618 / 'out-gki'):
        relative = 'out/' + path.relative_to(K618 / 'out-gki').as_posix()
    elif path.is_relative_to(K618):
        relative = path.relative_to(K618).as_posix()
    else:
        assert path.is_relative_to(ROOT / 'ports/ps5169'), path
        relative = 'sheng-ports/ps5169/' + path.relative_to(ROOT / 'ports/ps5169').as_posix()
    module_map[name] = relative
assert len(module_map) == 344
(configs / 'module-sources.json').write_text(json.dumps(module_map, indent=2) + '\n')
recipe = (UPSTREAM / 'kernel-6.18/k618_tp.sh').read_text()
table = recipe.split('REPOS=(', 1)[1].split('\n)', 1)[0]
entries = []
for value in re.findall(r'^\s*"([^"\n]+)"\s*$', table, re.M):
    parts = value.split('|')
    parts += [''] * (5 - len(parts))
    entries.append(parts)
(configs / 'techpacks.json').write_text(json.dumps(dict(
    multimedia_includes=re.search(r'MMINC="(.*?)"', recipe, re.S)[1],
    network_includes=re.search(r'RMINC="(.*?)"', recipe, re.S)[1], modules=entries), indent=2) + '\n')
tools = stage / 'tools'
tools.mkdir()
shutil.copyfile(UPSTREAM / 'kernel-6.18/k618_umh.c', tools / 'k618_umh.c')
rom = ROOT.parent / 'sheng-lineage/lineage-24.0'
shutil.copytree(rom / 'system/tools/mkbootimg', tools / 'mkbootimg',
                ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', 'tests'))
shutil.copyfile(rom / 'external/avb/avbtool.py', tools / 'avbtool.py')
provenance = stage / 'provenance'
provenance.mkdir()
for name in ('source-plan.json', 'sheng-release-cleanup.patch'):
    shutil.copyfile(PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18' / name, provenance / name)
shutil.copyfile(UPSTREAM / 'provenance/kernel-manifest.xml', provenance / 'kernel-manifest.xml')
shutil.copyfile(dest / 'build-result.json', provenance / 'tested-build.json')
shutil.copyfile(PROJECT / 'reports/kernel618-release-source.json', provenance / 'release-cleanup.json')
for relative, hashes in json.loads((provenance / 'release-cleanup.json').read_text())['changes'].items():
    exported = stage / 'k618' / relative
    assert hashlib.sha256(exported.read_bytes()).hexdigest() == hashes['after_sha256'], relative
(stage / 'README.md').write_text('''# Xiaomi Pad 6S Pro (sheng), 6.18.32 release

This is the adapted source snapshot used for release-r70 on stock HyperOS
OS3.0.303.0.WNXCNXM. Actual device boot completed successfully. The display
dependency group loads before camera, preserving the r69 white-screen fix.
Keyboard transport, real disconnect handling, pen, USB and charging fixes remain.

No out trees, object/module binaries, Git history, toolchains, ROM images,
rawdump logs or test captures are included. Required generated vendor configuration
headers and module loading lists ARE included because they are build inputs.
All 344 module paths are recorded in configs/module-sources.json.

Investigation logger CONFIG_SHENG_BOOTLOG is off. Diagnostic waits, register
sampling, scan watcher and keyboard informational logs were removed. Normal
kernel error reporting remains. The ACK GKI configuration retains DWARF/BTF and
ABI-related debug facilities required by the existing GKI module integration;
these are not the removed test logging. Stock boot arguments disable KASAN.
The unused KernelSU/SUSFS implementation and its build references are excluded.
Their disabled conditional integration guards remain in the adapted ACK source.

## Build on Linux / WSL2

Use Python 3.11+, make, rsync, cpio, kmod/depmod, flex, bison, libssl-dev,
libelf-dev, zstd and the pinned Google prebuilts from provenance/kernel-manifest.xml.
Required toolchain paths beneath PREBUILTS: clang/host/linux-x86/clang-r584948c,
rust-toolchain/linux-x86/1.91.1.p3, clang-tools/linux-x86,
kernel-build-tools/linux_musl-x86 and build-tools/linux-x86.
Install elfutils >= 0.193 with zstd support to ELFUTILS. The tested compiler is
Android Clang 22.0.1 (r584948c). Toolchain downloads are external dependencies.

```sh
python3.11 build_release.py --prebuilts /path/to/prebuilts \\
  --elfutils /path/to/elfutils-0.193 --jobs 8 \\
  --stock-boot /path/to/sheng_OS3.0.303_boot.img
```

The script builds the core, SoC, techpacks and tablet modules from the preserved
adapted sources, regenerates module metadata, embeds the module layer and checks
kernel export CRC consistency. With the read-only official boot template it also
packages out/boot.img with an unsigned AVB hash footer. Without --stock-boot,
it builds out/Image. It never flashes a device. Only use the matching stock
template; its required SHA256 is checked. A fresh build from this exported tree
has not been separately completed; the delivered boot.img was built and tested
from the matching original working tree. Rebuilds may differ in timestamps.

Individual upstream licensing files and SPDX identifiers remain in the source
trees. Repository revisions and release cleanup hashes are in provenance/.
''')

# Hash every regular source file and detect unwanted build products before tar.
subprocess.run([sys.executable, stage / 'build_release.py', '--prebuilts',
                K618 / 'ws/prebuilts', '--elfutils', ROOT / 'host-tools/elfutils-0.193-zstd',
                '--out', native / 'source-preflight', '--config-only'], check=True)
compile((stage / 'build_release.py').read_text(), 'build_release.py', 'exec')
assert (stage / 'k618/ws/common/Makefile').is_file()
assert (stage / 'k618/soc/gen/autoconf_vendor.h').is_file()
assert (modules / 'k618_batch.load').read_bytes() == (native / 'layer/lib/modules/k618_batch.load').read_bytes()
for name, relative in module_map.items():
    if relative.startswith('out/'):
        continue
    module_dir = (stage / 'k618' / relative).parent
    assert module_dir.is_dir(), (name, relative)
manifest = {}
for path in sorted(stage.rglob('*')):
    if path.is_symlink():
        assert not path.readlink().is_absolute(), path
        assert path.resolve().is_relative_to(stage), 'Escaping source link: ' + str(path)
    elif path.is_file():
        assert path.suffix not in ('.o', '.ko', '.pyc', '.img', '.cpio'), path
        with path.open('rb') as stream:
            manifest[path.relative_to(stage).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
(stage / 'SOURCE-SHA256.json').write_text(json.dumps(manifest, indent=2) + '\n')
archive = dest / (stage.name + '.tar.gz')
assert not archive.exists()
print('Compressing ' + str(len(manifest)) + ' source files', flush=True)
subprocess.run(['tar', '-czf', archive, '-C', export_parent, stage.name], check=True)
seen = set()
with tarfile.open(archive, 'r|gz') as stream:
    for member in stream:
        assert member.name.startswith(stage.name + '/') or member.name == stage.name
        relative = member.name[len(stage.name) + 1:]
        assert '..' not in Path(relative).parts and not Path(relative).is_absolute()
        if member.isfile() and relative in manifest:
            digest = hashlib.file_digest(stream.extractfile(member), 'sha256').hexdigest()
            assert digest == manifest[relative], relative
            seen.add(relative)
assert seen == set(manifest), 'Incomplete archive'
with archive.open('rb') as stream:
    archive_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
report = dict(revision=args.revision, source_files=len(manifest),
              source_bytes=sum(p.stat().st_size for p in stage.rglob('*') if p.is_file() and not p.is_symlink()),
              archive_bytes=archive.stat().st_size, archive_sha256=archive_sha,
              output=str(archive), excluded=excludes, module_count=344,
              source_hash_readback_verified=True, device_boot_verified=True,
              clean_export_configuration_verified=True, clean_export_rebuild_verified=False)
(dest / 'source-package.json').write_text(json.dumps(report, indent=2) + '\n')
with (dest / 'SHA256SUMS').open('a') as stream:
    stream.write(archive_sha + '  ' + archive.name + '\n')
print(json.dumps(report, indent=2), flush=True)
