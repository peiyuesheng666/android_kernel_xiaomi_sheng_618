#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch pinned sheng board sources into a separate Linux build directory.

This prepares reference sources only. It does not apply phone patches, build
a kernel, delete existing files, access stock firmware, or flash a device.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True,
                          env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'}).stdout.strip()


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/root/sheng-618'))
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--catalog-only', action='store_true',
                        help='Fetch Git trees without checking out large kernel sources')
    parser.add_argument('--component', action='append')
    args = parser.parse_args()
    plan = json.loads((project / 'device/xiaomi/sheng/interfaces/kernel/6.18/source-plan.json').read_text())
    if os.name != 'posix':
        parser.error('Run this source preparation in Linux/WSL')
    root = args.root.resolve()
    if root == Path('/') or root == Path.home() or root.is_relative_to(Path('/mnt')):
        parser.error('Choose a separate native Linux build directory')
    ancestor = root
    while not ancestor.exists():
        ancestor = ancestor.parent
    linux_free = shutil.disk_usage(ancestor).free
    host_free = shutil.disk_usage('/mnt/c').free if Path('/mnt/c').exists() else linux_free
    required_gib = 2 if args.catalog_only else plan['minimum_host_free_gib']
    minimum = required_gib * 1024**3
    print(json.dumps({'root': str(root), 'linux_free_gib': round(linux_free / 1024**3, 2),
                      'host_free_gib': round(host_free / 1024**3, 2),
                      'required_host_free_gib': required_gib,
                      'catalog_only': args.catalog_only,
                      'space_passed': min(linux_free, host_free) >= minimum,
                      'full_port_space_passed': min(linux_free, host_free) >= plan['minimum_host_free_gib'] * 1024**3}))
    if min(linux_free, host_free) < minimum:
        return 2
    if args.preflight:
        return 0
    components = plan['board_sources']
    if args.component:
        unknown = set(args.component) - {x['name'] for x in components}
        if unknown:
            parser.error(f'Unknown components: {sorted(unknown)}')
        components = [x for x in components if x['name'] in args.component]
    marker = root / '.sheng-kernel618-source-root'
    if root.exists() and any(root.iterdir()) and not marker.is_file():
        parser.error('Existing nonempty root has no sheng source marker')
    root.mkdir(parents=True, exist_ok=True)
    marker.touch()
    receipt = root / 'board-source-receipt.json'
    records = {x['name']: x for x in json.loads(receipt.read_text())} if receipt.exists() else {}
    # A changed source selection withdraws old receipts without deleting caches.
    records = {name: item for name, item in records.items()
               if name in {x['name'] for x in plan['board_sources']}}
    for spec in components:
        destination = root / 'src' / spec['name']
        is_catalog = not destination.exists() or records.get(spec['name'], {}).get('catalog_only', False)
        if destination.exists():
            # Never reset or clean a checkout someone has already edited.
            if run('git', '-C', str(destination), 'rev-parse', 'HEAD') != spec['revision']:
                raise ValueError(f'Existing source revision differs: {destination}')
            catalog = records.get(spec['name'], {}).get('catalog_only', False)
            if catalog:
                if any(p.name != '.git' for p in destination.iterdir()):
                    raise ValueError(f'Source files added to a catalog checkout: {destination}')
            elif run('git', '-C', str(destination), 'status', '--porcelain'):
                raise ValueError(f'Existing source has local changes: {destination}')
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            run('git', 'clone', '--filter=blob:none', '--no-checkout', '--depth', '1',
                '--branch', spec['branch'], '--single-branch', spec['url'], str(destination))
            if run('git', '-C', str(destination), 'rev-parse', 'HEAD') != spec['revision']:
                run('git', '-C', str(destination), 'fetch', '--depth', '1', 'origin', spec['revision'])
        if not args.catalog_only:
            run('git', '-C', str(destination), 'checkout', '--detach', spec['revision'])
            is_catalog = False
        elif run('git', '-C', str(destination), 'rev-parse', 'HEAD') != spec['revision']:
            # New no-checkout clone whose upstream branch moved since pinning.
            run('git', '-C', str(destination), 'update-ref', 'HEAD', spec['revision'])
        records[spec['name']] = {**spec, 'path': str(destination),
                                'catalog_only': is_catalog,
                                'checked_revision':
                                run('git', '-C', str(destination), 'rev-parse', 'HEAD')}
        receipt.write_text(json.dumps(list(records.values()), indent=2) + '\n')
        print(f"Ready reference {'catalog' if args.catalog_only else 'source'}: {spec['name']} {spec['revision']}", flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
