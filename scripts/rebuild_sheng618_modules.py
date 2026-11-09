#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebuild preserved adaptations directly, without replaying source/config recipes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from build_sheng618_upstream import ACK, CLANG, K618, LOGS, OUT, PROJECT, ROOT, TOOLS, UPSTREAM, environment
from sheng618_build_identity import configure, verify, LOCAL_SUFFIX
from audit_kernel618_modules import ElfModule
from sheng618_fastrpc_config import build_flags as rpc_build_flags, verify_imports as verify_rpc_imports
from sheng618_fastrpc_config import EVA_REQUIRED_IMPORTS
from sheng618_ssphy_pipe_xo import verify as verify_ssphy_pipe_xo
from sheng618_camera_io_stride import verify as verify_camera_io_stride
from sheng618_usb_charger_abi import verify as verify_usb_charger_abi

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', required=True)
parser.add_argument('--phase', choices=['kernel', 'soc', 'techpacks', 'tablet', 'manifest', 'all'], default='all')
parser.add_argument('--jobs', type=int, default=os.cpu_count())
parser.add_argument('--techpack', help='Rebuild only this named table entry during the techpacks phase')
options = parser.parse_args()
assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}', options.tag)
assert options.jobs > 0
env = environment(options.jobs)
native = ROOT / 'diagnostic' / options.tag
native.mkdir(parents=True, exist_ok=True)
expected_release = '6.18.32' + LOCAL_SUFFIX
soc = K618 / 'soc'
tp = K618 / 'vendor/qcom/opensource'
logs = native / 'rebuild-logs'
logs.mkdir(exist_ok=True)
make = ['make', '-C', ACK, 'O=' + str(OUT), 'ARCH=arm64', 'LLVM=1', 'LLVM_IAS=1',
        'PAHOLE=' + str(TOOLS / 'kernel-build-tools/linux_musl-x86/bin/pahole'),
        '-j' + str(options.jobs)]


def run(label, args):
    print('[build] ' + label, flush=True)
    with (logs / (label + '.log')).open('w') as stream:
        result = subprocess.run(list(map(str, args)), env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print('\n'.join((logs / (label + '.log')).read_text(errors='replace').splitlines()[-45:]), flush=True)
        raise SystemExit(result.returncode)
    print('[complete] ' + label, flush=True)


def kernel():
    # Preserve the adapted .config, applying the requested identity and root policy.
    for output in (OUT, K618 / 'out-gki-ir'):
        shutil.copyfile(output / '.config', native / (output.name + '-config-before'))
        configure(ACK, output, PROJECT)
    shutil.copyfile(PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng_bootlog.c',
                    ACK / 'drivers/misc/sheng_bootlog.c')
    run('kernel-config', [*make, 'olddefconfig'])
    run('kernel', [*make, 'Image', 'modules'])
    print(json.dumps(verify(OUT, expected_release)), flush=True)


def soc_modules():
    run('soc', [*make, 'M=' + str(soc), 'modules'])
    verify_ssphy_pipe_xo(soc / 'phy-msm-ssusb-qmp.ko', PROJECT, K618)
    verify_usb_charger_abi(soc / 'qti_battery_charger.ko', PROJECT, K618)


def techpacks():
    recipe = (UPSTREAM / 'kernel-6.18/k618_tp.sh').read_text()
    # Read only the fixed table and include lists. Never execute its fix-up recipes.
    mm = re.search(r'MMINC="(.*?)"', recipe, re.S)[1]
    rm = re.search(r'RMINC="(.*?)"', recipe, re.S)[1]
    table = recipe.split('REPOS=(', 1)[1].split('\n)', 1)[0]
    for entry in re.findall(r'^\s*"([^"\n]+)"\s*$', table, re.M):
        parts = entry.split('|')
        parts += [''] * (5 - len(parts))
        name, directory, variables, incs, defs = parts
        if name in ('video', 'eva'):
            continue
        if options.techpack and options.techpack != name:
            continue
        stage = (tp / directory).resolve()
        assert stage.is_dir(), stage
        values = {'%M': mm, '%R': rm, '%C': 'CONFIG_ARCH_CANOE=y',
                  '%L': '-DCONFIG_RMNET_LA_PLATFORM=1', '%I': '-DCONFIG_IPA3=1',
                  '%D': str(stage), '%P': str(stage.parent), '%T': str(tp), '%W': str(ACK)}

        def expand(value):
            value = value.replace('${NFC_TRACE:+-DK618_NFC_TRACE}', '')
            for old, new in values.items():
                value = value.replace(old, new)
            assert not re.search(r'%[A-Z]|\$[({]', value), value
            return value

        syms = [soc / 'Module.symvers']
        syms += sorted(p for p in (K618 / 'tp-log').glob('*.symvers') if p.stem != name)
        if name == 'eva515':
            # EVA consumes the actual 5.15 RPC provider used by sheng, whose
            # driver/device structures differ from the generic 6.12 provider.
            legacy = K618 / 'vendor/xiaomi/adsprpc-515'
            run('rpc-before-eva', [*make, 'M=' + str(legacy), 'modules', 'SOC=' + str(soc),
                'KBUILD_EXTRA_SYMBOLS=' + str(soc / 'Module.symvers'), *rpc_build_flags(K618)])
            verify_rpc_imports(legacy / 'frpc-adsprpc.ko')
            incs = str(legacy / 'include') + ' ' + incs
            defs += ' -DCONFIG_MSM_ADSPRPC=1'
            syms = [p for p in syms if p.name != 'dsp.symvers'] + [legacy / 'Module.symvers']
        args = [*make, 'M=' + str(stage), 'modules', 'KERNEL_SRC=' + str(ACK),
                'KERNEL_ROOT=' + str(ACK), 'CONFIG_ARCH_KALAMA=y',
                'KBUILD_EXTRA_SYMBOLS=' + ' '.join(map(str, syms)),
                'NOSTDINC_FLAGS=-nostdinc -I' + str(soc / 'include') + ' -I' + str(soc / 'include/uapi') +
                ''.join(' -I' + x for x in expand(incs).split()),
                'KCFLAGS=-Wno-error -include ' + str(K618 / 'tp-autoconf.h') + ' ' + expand(defs),
                *shlex.split(expand(variables))]
        run('tp-' + name, args)
        if name == 'camera':
            verify_camera_io_stride(stage / 'camera.ko', PROJECT, K618)
        if name == 'eva515':
            verify_rpc_imports(stage / 'msm/msm-eva.ko', EVA_REQUIRED_IMPORTS)
        shutil.copyfile(stage / 'Module.symvers', K618 / 'tp-log' / (name + '.symvers'))


def tablet():
    syms = [soc / 'Module.symvers', *sorted((K618 / 'tp-log').glob('*.symvers'))]
    stages = [K618 / 'sheng-ports' / group for group in ('pogo', 'cs35l43', 'touch', 'fingerprint', 'hall', 'keyboard')]
    stages += [ROOT / 'ports/ps5169', K618 / 'vendor/xiaomi/adsprpc-515', K618 / 'mark']
    for stage in stages:
        extra = rpc_build_flags(K618) if stage.name == 'adsprpc-515' else []
        run('native-' + stage.name, [*make, 'M=' + str(stage), 'modules', 'SOC=' + str(soc),
            'KBUILD_EXTRA_SYMBOLS=' + ' '.join(map(str, syms)), *extra])
        if stage.name == 'adsprpc-515':
            verify_rpc_imports(stage / 'frpc-adsprpc.ko')
        syms.append(stage / 'Module.symvers')


def manifest():
    verify(OUT, expected_release)
    baseline = ROOT / 'diagnostic/hardware-r32/layer/lib/modules'
    sources = {}
    roots = [OUT, soc, K618 / 'vendor', K618 / 'sheng-ports', K618 / 'mark', ROOT / 'ports/ps5169']
    for root in roots:
        for path in root.rglob('*.ko'):
            sources.setdefault(path.name, []).append(path)
    preferred = {name: soc / name for name in ('qmi_helpers.ko', 'pdr_interface.ko', 'qcom_pdr_msg.ko')}
    preferred['frpc-adsprpc.ko'] = K618 / 'vendor/xiaomi/adsprpc-515/frpc-adsprpc.ko'
    rpc_check = verify_rpc_imports(preferred['frpc-adsprpc.ko'])
    eva_check = verify_rpc_imports(tp / 'eva-kernel-515/msm/msm-eva.ko', EVA_REQUIRED_IMPORTS)
    ssphy_check = verify_ssphy_pipe_xo(soc / 'phy-msm-ssusb-qmp.ko', PROJECT, K618)
    camera_check = verify_camera_io_stride(tp / 'camera-kernel/camera.ko', PROJECT, K618)
    charger_check = verify_usb_charger_abi(soc / 'qti_battery_charger.ko', PROJECT, K618)
    result = {}
    for old in sorted(baseline.glob('*.ko')):
        key = 'kiwi_v2.ko' if old.name == 'qca_cld3_kiwi_v2.ko' else old.name
        candidates = sources.get(key, [])
        if old.name in preferred:
            source = preferred[old.name]
            assert source in candidates
        else:
            assert len(candidates) == 1, (old.name, list(map(str, candidates)))
            source = candidates[0]
        # Parse the target ELF, avoiding host libkmod's builtin-name collisions
        # (notably sg, which otherwise reports the WSL host's builtin metadata).
        values = ElfModule(source).info['vermagic']
        assert len(values) == 1, (source, values)
        vermagic = values[0]
        assert vermagic.split()[0] == expected_release, (source, vermagic)
        result[old.name] = dict(source=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(), vermagic=vermagic)
    assert len(result) == 344, len(result)
    report = dict(revision=options.tag, release=expected_release, modules=result,
                  module_count=len(result), binary_vermagic_rewriting=False,
                  fastrpc_vendor_api_check=rpc_check,
                  eva_fastrpc_api_check=eva_check,
                  ssphy_pipe_xo_api_check=ssphy_check,
                  camera_io_stride_check=camera_check,
                  usb_charger_abi_check=charger_check,
                  compiler_version_full=subprocess.check_output([CLANG / 'clang', '--version'], text=True))
    destination = native / 'all-modules.json'
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(str(destination), flush=True)


phases = dict(kernel=kernel, soc=soc_modules, techpacks=techpacks, tablet=tablet, manifest=manifest)
for phase in phases if options.phase == 'all' else [options.phase]:
    phases[phase]()
