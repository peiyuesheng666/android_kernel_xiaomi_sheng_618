#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebuild staged native modules without replaying upstream phone patches."""
import argparse
from build_sheng618_upstream import ACK, K618, command, environment, make_args

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('group', choices=['touch', 'audio', 'battery'])
parser.add_argument('--jobs', type=int, default=24)
options = parser.parse_args()
assert 1 <= options.jobs <= 128
jobs = options.jobs
env = environment(jobs)
soc = K618 / 'soc'

if options.group == 'touch':
    stage = K618 / 'sheng-ports/touch'
    symbols = [soc / 'Module.symvers']
    symbols += sorted((K618 / 'vendor').rglob('Module.symvers'))
    args = make_args(stage, jobs) + ['KBUILD_EXTRA_SYMBOLS=' + ' '.join(map(str, symbols))]
elif options.group == 'battery':
    # A single .ko target replaces modules.order with one entry and breaks modpost
    # for consumers of other SoC exports. Always rebuild the complete SoC target.
    (soc / 'modules.order').unlink(missing_ok=True)
    args = make_args(soc, jobs)
else:
    stage = K618 / 'vendor/qcom/opensource/audio-kernel'
    symbols = [soc / 'Module.symvers']
    symbols += [p for p in sorted((K618 / 'tp-log').glob('*.symvers'))
                if p.name != 'audio.symvers']
    includes = [soc / 'include', soc / 'include/uapi']
    tp = K618 / 'vendor/qcom/opensource'
    includes += [tp / p for p in [
        'synx-kernel/msm/synx', 'synx-kernel/include', 'synx-kernel/include/uapi',
        'synx-kernel/include/uapi/synx/media', 'mm-drivers/hw_fence/include',
        'mm-drivers/hfi_core/inc', 'mm-drivers/msm_ext_display/include',
        'mm-drivers/sync_fence/include', 'securemsm-kernel/hdcp',
        'securemsm-kernel/include', 'securemsm-kernel/include/linux', 'dsp-kernel/include']]
    args = make_args(stage, jobs) + [
        'KERNEL_SRC=' + str(ACK), 'KERNEL_ROOT=' + str(ACK),
        'CONFIG_ARCH_KALAMA=y', 'AUDIO_ROOT=' + str(stage), 'MODNAME=audio_dlkm',
        'KBUILD_EXTRA_SYMBOLS=' + ' '.join(map(str, symbols)),
        'NOSTDINC_FLAGS=-nostdinc ' + ' '.join('-I' + str(p) for p in includes),
        'KCFLAGS=-Wno-error -include ' + str(K618 / 'tp-autoconf.h')]
command('native-' + options.group, args, env)
