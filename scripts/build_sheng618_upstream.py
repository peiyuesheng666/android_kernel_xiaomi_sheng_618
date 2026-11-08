#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the selected SM8550 integration and reuse the existing sheng driver sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from audit_kernel618_modules import ElfModule, check_candidate

PROJECT = Path(__file__).resolve().parents[1]
PLAN = json.loads((PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/source-plan.json').read_text())
ROOT = Path(PLAN['build_root'])
BUILD = ROOT / 'upstream-build'
UPSTREAM = ROOT / 'upstream-project'
K618 = BUILD / 'k618'
ACK = K618 / 'ws/common'
OUT = K618 / 'out-gki'
TOOLS = K618 / 'ws/prebuilts'
CLANG = TOOLS / 'clang/host/linux-x86/clang-r584948c/bin'
RUST = TOOLS / 'rust-toolchain/linux-x86/1.91.1.p3'
HOST = ROOT / 'host-tools/elfutils-0.193-zstd'
LOGS = ROOT / 'logs'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def environment(jobs):
    # The Ubuntu 22.04 libdw cannot build ACK's gendwarfksyms; use the already
    # built private elfutils, without replacing the machine's system libraries.
    flags = ('HOSTCFLAGS=-O2\\ -I' + str(HOST / 'include') + ' HOSTLDFLAGS=-L' +
             str(HOST / 'lib') + '\\ -Wl,-rpath,' + str(HOST / 'lib'))
    return {**os.environ, 'NB': str(BUILD), 'K618': str(K618), 'BUILD_ROOT': str(BUILD),
            'JOBS': str(jobs), 'TAG': 'sheng', 'KBUILD_GENDWARFKSYMS_STABLE': '1',
            'LIBCLANG_PATH': str(CLANG.parent / 'lib'), 'RUSTC_BOOTSTRAP': '1',
            'RUST_LIB_SRC': str(RUST / 'lib/rustlib/src/rust/library'),
            'MAKEFLAGS': flags,
            'PATH': ':'.join(map(str, [CLANG, RUST / 'bin', TOOLS / 'clang-tools/linux-x86/bin',
                                      TOOLS / 'kernel-build-tools/linux_musl-x86/bin',
                                      TOOLS / 'build-tools/linux-x86/bin'])) + ':/usr/sbin:/usr/bin:/sbin:/bin'}


def command(name, args, env):
    log = LOGS / ('upstream-' + name + '.log')
    print('[build] ' + name + ': ' + str(log), flush=True)
    with log.open('w') as stream:
        result = subprocess.run(list(map(str, args)), env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print('\n'.join(log.read_text(errors='replace').splitlines()[-45:]), flush=True)
        raise SystemExit(result.returncode)
    print('[complete] ' + name, flush=True)


def make_args(stage, jobs):
    return ['make', '-C', ACK, 'O=' + str(OUT), 'M=' + str(stage), 'ARCH=arm64',
            'LLVM=1', 'LLVM_IAS=1', '-j' + str(jobs), 'modules']


def tablet(jobs, env):
    # Reuse the earlier, hash-verified source adaptations, rebuilding only the
    # objects against this integration's actual kernel ABI. Leave the old .ko intact.
    symbols = [K618 / 'soc/Module.symvers']
    symbols += sorted((K618 / 'vendor').rglob('Module.symvers'))
    for group in ('pogo', 'cs35l43'):
        old = ROOT / 'ports' / group
        receipt = json.loads((old / 'source-receipt.json').read_text())
        stage = K618 / 'sheng-ports' / group
        for relative, expected in receipt['generated_sha256'].items():
            source = old / relative
            if sha(source) != expected:
                raise ValueError('Earlier driver source changed: ' + str(source))
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or sha(target) != expected:
                shutil.copy2(source, target)
        shutil.copy2(old / 'source-receipt.json', stage / 'source-receipt.json')
        command('tablet-' + group, make_args(stage, jobs) +
                ['KBUILD_EXTRA_SYMBOLS=' + ' '.join(map(str, symbols))], env)
        symbols.append(stage / 'Module.symvers')


def image(jobs, env):
    hardware = Path('/root/sheng-lineage/firmware-dump/hardware')
    first = hardware / 'modules/vendor_boot'
    second = hardware / 'modules/vendor_dlkm/modules.load'
    tablet_modules = sorted((K618 / 'sheng-ports').rglob('*.ko'))
    if not tablet_modules:
        raise ValueError('Build the preserved tablet drivers first')
    # Use upstream's module-layer generator and relinker. Only sheng's own
    # first/second-stage lists and init_boot are inputs. The generic ramdisk is
    # used internally by that generator; only its /lib/modules layer is embedded.
    layer_env = {**env, 'STOCK': str(first), 'STAGE2': str(second),
                 'MKB': str(BUILD / 'home/mkbootimg'), 'BATCH': '1',
                 'EXTRA': str(UPSTREAM / 'kernel-6.18/k618_load.c'),
                 'LAST': 'k618_load', 'PANICSIG': '', 'TPMODS': '1',
                 'GKIMODS': 'zram zsmalloc rfkill libarc4',
                 'MADRIDMODS': ' '.join(map(str, tablet_modules)),
                 'OPTS': 'k618_load list=/lib/modules/k618_batch.load dir=/lib/modules helper=/k618_umh',
                 'RENAME': 'ucsi_glink=ucsi_qti_glink qca_cld3_kiwi_v2=kiwi_v2 ufs_qcom=ufs_qcom'}
    command('module-layer', ['bash', UPSTREAM / 'kernel-6.18/k618_bootimg.sh',
                            hardware / 'boot-images/init_boot.img'], layer_env)
    stage = K618 / 'boot-test/stage/rd/lib/modules'
    dependency_file = stage / 'modules.dep'
    if not dependency_file.exists() or not dependency_file.stat().st_size:
        raise ValueError('Module dependency metadata was not generated')
    command('layer-crc', ['python3', UPSTREAM / 'kernel-6.18/k618_stage_crc.py',
                         OUT / 'Module.symvers', stage], env)
    checked = check_candidate({p.name: ElfModule(p) for p in stage.glob('*.ko')},
                              {'source_keep_modules': ['zram.ko', 'zsmalloc.ko']}, OUT,
                              [stage / 'zram.ko', stage / 'zsmalloc.ko'], '6.18')
    (PROJECT / 'reports/kernel618-upstream-layer.json').write_text(json.dumps(checked, indent=2) + '\n')
    if not checked['abi_passed']:
        raise ValueError('Module layer is not closed: ' + json.dumps(checked['issue_counts']))
    modules = {p.name for p in stage.glob('*.ko')}
    listed = {Path(line.split(':', 1)[0]).name for line in dependency_file.read_text().splitlines()}
    if modules != listed:
        raise ValueError('Module dependency metadata does not cover the complete layer')
    command('embedded-image', ['bash', UPSTREAM / 'kernel-6.18/k618_irbuild.sh'], env)
    source = K618 / 'out-gki-ir/arch/arm64/boot/Image'
    if source.read_bytes()[56:60] != b'ARM\x64':
        raise ValueError('Not a raw ARM64 Image')
    destination = PROJECT / 'artifacts/sheng-6.18-first-boot'
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination / 'Image')
    missing = (K618 / 'boot-test/first-stage-missing.txt').read_text().splitlines()
    report = {'schema': 1, 'image': str(destination / 'Image'), 'sha256': sha(source),
              'bytes': source.stat().st_size, 'rom': PLAN['primary_rom'],
              'upstream_revision': PLAN['reference']['revision'],
              'module_layer_embedded': True, 'module_count': len(list(stage.glob('*.ko'))),
              'first_stage_missing': missing, 'runtime_validated': False,
              'purpose': 'Experimental first-boot test; tablet hardware functionality not validated',
              'known_incomplete_tablet_drivers': ['nt36532_touch', 'metis', 'nanosic_driver',
                                                  'xiaomi_keyboard_driver', 'xiaomi_hall'],
              'module_dependencies_sha256': sha(dependency_file),
              'versioned_imports_checked': checked['versioned_imports_checked'],
              'tablet_modules': [path.name for path in tablet_modules]}
    (PROJECT / 'reports/kernel618-upstream-image.json').write_text(json.dumps(report, indent=2) + '\n')
    (destination / 'SHA256SUMS').write_text(report['sha256'] + '  Image\n')
    print('Image: ' + str(destination / 'Image'), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['kernel', 'soc', 'techpack', 'tablet', 'image', 'all'])
    parser.add_argument('--jobs', type=int, default=os.cpu_count())
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    if not (BUILD / '.sheng-upstream-build').is_file():
        parser.error('Run prepare_sheng618_upstream.py first')
    revision = subprocess.check_output(['git', '-C', str(UPSTREAM), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != PLAN['reference']['revision']:
        raise ValueError('Unexpected upstream integration revision')
    env = environment(args.jobs)
    phases = ['kernel', 'soc', 'techpack', 'tablet', 'image'] if args.phase == 'all' else [args.phase]
    recipes = {'kernel': 'k618_gki.sh', 'soc': 'k618_stage2.sh', 'techpack': 'k618_tp.sh'}
    for phase in phases:
        if phase == 'tablet':
            tablet(args.jobs, env)
        elif phase == 'image':
            image(args.jobs, env)
        else:
            command(phase, ['bash', UPSTREAM / 'kernel-6.18' / recipes[phase], str(args.jobs)], env)
        receipt = {'phase': phase, 'upstream_revision': revision, 'build_root': str(BUILD),
                   'rom_target': 'HyperOS', 'hardware_validated': False}
        if phase == 'kernel':
            kernel_image = OUT / 'arch/arm64/boot/Image'
            if kernel_image.read_bytes()[56:60] != b'ARM\x64':
                raise ValueError('Not a raw ARM64 Image')
            receipt.update(image=str(kernel_image), image_sha256=sha(kernel_image),
                           module_layer_embedded=False,
                           delivery_ready=False)
        (LOGS / ('upstream-' + phase + '-result.json')).write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
