#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reconstruct the user-selected SM8550 integration without changing earlier work."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/source-plan.json'
PLAN = json.loads(PLAN_PATH.read_text())
ROOT = Path(PLAN['build_root'])
UPSTREAM = ROOT / 'upstream-project'
BUILD = ROOT / 'upstream-build'


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', choices=['soc', 'sources', 'vendor'], default='soc')
    args = parser.parse_args()
    spec = PLAN['reference']
    cache = PROJECT / 'tools/nuwa-k618-reference'
    if not UPSTREAM.exists():
        if git(cache, 'rev-parse', 'HEAD') != spec['revision'] or git(cache, 'status', '--porcelain'):
            raise ValueError('Reference cache must be clean and pinned')
        run('git', 'clone', '--no-hardlinks', '--quiet', cache, UPSTREAM)
        run('git', '-C', UPSTREAM, 'remote', 'set-url', 'origin', spec['url'])
    if git(UPSTREAM, 'rev-parse', 'HEAD') != spec['revision']:
        raise ValueError('Unexpected integration revision; preserve the checkout for inspection')
    marker = BUILD / '.sheng-upstream-build'
    if not marker.exists():
        if BUILD.exists() and any(BUILD.iterdir()):
            raise ValueError('Refuse to adopt an unmarked nonempty build directory')
        BUILD.mkdir(parents=True, exist_ok=True)
        marker.write_text(spec['revision'] + '\n')
    elif marker.read_text().strip() != spec['revision']:
        raise ValueError('Build directory belongs to another integration revision')
    os.environ.update(BUILD_ROOT=str(BUILD), JOBS='4')
    sys.path.insert(0, str(UPSTREAM / 'scripts'))
    module_spec = importlib.util.spec_from_file_location('nuwa_bootstrap', UPSTREAM / 'scripts/bootstrap-inputs.py')
    bootstrap = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(bootstrap)
    receipts = []
    if args.only != 'vendor':
        for item in bootstrap.SPEC['repositories']:
            if args.only == 'soc' and item['name'] not in ('ACK', 'SoC'):
                continue
            destination = BUILD / item['path']
            if item['name'] == 'ACK' and not destination.exists():
                # Separate working tree; share only immutable Git objects with the clean baseline.
                destination.parent.mkdir(parents=True, exist_ok=True)
                run('git', 'clone', '--quiet', '--shared', '--no-checkout', ROOT / 'src/ack', destination)
                run('git', '-C', destination, 'remote', 'set-url', 'origin', item['url'])
            print('[reuse upstream] ' + item['name'], flush=True)
            bootstrap.checkout(item)
            receipts.append({'name': item['name'], 'path': str(destination),
                             'revision': git(destination, 'rev-parse', 'HEAD'),
                             'tree': git(destination, 'rev-parse', 'HEAD^{tree}')})
    if args.only in ('vendor', 'sources'):
        bootstrap.vendor_cache()
        if args.only == 'sources':
            run('bash', UPSTREAM / 'kernel-6.18/k618_tp_get.sh', env={**os.environ,
                'NB': str(BUILD), 'K618': str(BUILD / 'k618')})
    report = {'schema': 1, 'upstream': spec, 'build_root': str(BUILD),
              'operation': args.only, 'repositories': receipts,
              'rom_target': 'HyperOS', 'output_target': 'Image',
              'earlier_port_root_preserved': str(ROOT / 'ports'),
              'hardware_validated': False}
    target = PROJECT / 'reports' / f'kernel618-upstream-{args.only}.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Prepared: ' + str(target), flush=True)


if __name__ == '__main__':
    main()
