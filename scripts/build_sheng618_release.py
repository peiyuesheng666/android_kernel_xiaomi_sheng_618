#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build release modules from the tested tree and preserve r69's module order."""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from build_sheng618_upstream import ACK, K618, OUT, PROJECT, ROOT, UPSTREAM, environment, make_args

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', default='release-r70')
parser.add_argument('--base', default='hardware-r69')
args = parser.parse_args()
assert re.fullmatch(r'release-r[0-9]+', args.tag)
subprocess.run([sys.executable, PROJECT / 'scripts/prepare_sheng618_release.py'], check=True)
jobs = os.cpu_count()


def build(name, command):
    log = ROOT / 'logs' / (args.tag + '-' + name + '.log')
    print('Building release ' + name + ': ' + str(log), flush=True)
    with log.open('w') as stream:
        result = subprocess.run(command, env=environment(jobs), stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print('\n'.join(log.read_text(errors='replace').splitlines()[-55:]), flush=True)
        raise SystemExit(result.returncode)


build('soc', make_args(K618 / 'soc', jobs))
build('keyboard', make_args(K618 / 'sheng-ports/keyboard', jobs) +
      ['KBUILD_EXTRA_SYMBOLS=' + str(K618 / 'soc/Module.symvers')])
build('loader', make_args(K618 / 'mark', jobs))
stage = K618 / 'vendor/qcom/opensource/display-drivers'
recipe = (UPSTREAM / 'kernel-6.18/k618_tp.sh').read_text()
mm = re.search(r'MMINC="(.*?)"', recipe, re.S)[1]
table = recipe.split('REPOS=(', 1)[1].split('\n)', 1)[0]
entry, = [value for value in re.findall(r'^\s*"([^"\n]+)"\s*$', table, re.M)
          if value.startswith('display|')]
_, directory, variables, incs, defs = entry.split('|')


def expand(value):
    for old, new in {'%M': mm, '%D': str(stage), '%P': str(stage.parent),
                     '%T': str(stage.parent), '%W': str(ACK)}.items():
        value = value.replace(old, new)
    assert not re.search(r'%[A-Z]|\$[({]', value), value
    return value


symbols = [K618 / 'soc/Module.symvers']
symbols += sorted(path for path in (K618 / 'tp-log').glob('*.symvers') if path.stem != 'display')
command = make_args(stage, jobs) + ['CONFIG_ARCH_KALAMA=y',
    'KBUILD_EXTRA_SYMBOLS=' + ' '.join(map(str, symbols)),
    'NOSTDINC_FLAGS=-nostdinc -I' + str(K618 / 'soc/include') +
    ' -I' + str(K618 / 'soc/include/uapi') + ''.join(' -I' + path for path in expand(incs).split()),
    'KCFLAGS=-Wno-error -include ' + str(K618 / 'tp-autoconf.h') + ' ' + expand(defs),
    *shlex.split(expand(variables))]
build('display', command)
replacements = {
    'arm_smmu.ko': K618 / 'soc/arm_smmu.ko',
    'dispcc-kalama.ko': K618 / 'soc/dispcc-kalama.ko',
    'qti_battery_charger.ko': K618 / 'soc/qti_battery_charger.ko',
    'nanosic_driver.ko': K618 / 'sheng-ports/keyboard/nanosic_driver.ko',
    'msm_drm.ko': stage / 'msm/msm_drm.ko',
    'k618_load.ko': K618 / 'mark/k618_load.ko',
}
subprocess.run([sys.executable, PROJECT / 'scripts/build_sheng618_layer_variant.py',
    '--tag', args.tag, '--base', args.base, '--release',
    *[arg for name, source in replacements.items() for arg in ('--replace', name + '=' + str(source))]], check=True)
native = ROOT / 'diagnostic' / args.tag
base = ROOT / 'diagnostic' / args.base
assert (native / 'layer/lib/modules/k618_batch.load').read_bytes() == (base / 'layer/lib/modules/k618_batch.load').read_bytes()
modules = list((native / 'layer/lib/modules').glob('*.ko'))
assert len(modules) == 344
for module in modules:
    data = module.read_bytes()
    for marker in (b'sheng early scan:', b'sheng smmu trace:', b'sheng_display_probe:',
                   b'TEST_ONLY', b'sheng_handoff:', b'sheng_nanosic charger keyboard_plugin=',
                   b'sheng_scan_watch_ms', b'sheng_postclock_hold_ms', b'sheng_before_display_hold_ms'):
        assert marker not in data, (module.name, marker)
print('Release built: 344 modules, diagnostics absent, r69 order preserved', flush=True)
