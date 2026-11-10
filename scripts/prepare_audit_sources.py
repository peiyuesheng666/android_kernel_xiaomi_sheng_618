#!/usr/bin/env python3
"""Keep audit-only sparse source checkouts separate from the ACK build tree."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess

PROJECT = Path(__file__).resolve().parents[1]
BASE = Path('/root/sheng-source-inputs/reference')
SPECS = [
    ('micode-kernel', 'MiCode/Xiaomi_Kernel_OpenSource', 'sheng-u-oss'),
    ('micode-devicetree', 'MiCode/kernel_devicetree', 'sheng-u-oss'),
    ('lineage-kernel', 'LineageOS/android_kernel_xiaomi_sm8550', 'lineage-23.2'),
    ('lineage-modules', 'LineageOS/android_kernel_xiaomi_sm8550-modules', 'lineage-23.2'),
    ('lineage-devicetrees', 'LineageOS/android_kernel_xiaomi_sm8550-devicetrees', 'lineage-23.2'),
    ('lineage-common', 'LineageOS/android_device_xiaomi_sm8550-common', 'lineage-23.2'),
]
ENV = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null')
PATTERNS = ['/*', '!/*/', '**/Makefile', '**/Kbuild', '**/Kconfig*', '**/*.mk', '**/*.bzl',
            '**/*.config', '**/*defconfig', '**/AGENTS.md', '**/README*', '**/COPYING*', '**/LICENSE*']

def git(path, *args, **kwargs):
    return subprocess.run(['git', '-C', str(path), *args], env=ENV, check=True, text=True, **kwargs)

def prepare(spec):
    name, repo, branch = spec
    path = BASE / name
    url = f'https://github.com/{repo}.git'
    log_path = Path('/root/sheng-source-inputs/logs') / f'audit-fetch-{name}.log'
    with log_path.open('w') as log:
        if not (path / '.git').is_dir():
            subprocess.run(['git', 'clone', '--filter=blob:none', '--depth=1', '--single-branch',
                            '--no-checkout', '--branch', branch, url, str(path)], env=ENV,
                           check=True, stdout=log, stderr=log, timeout=600)
        git(path, 'sparse-checkout', 'init', '--no-cone', stdout=log, stderr=log)
        git(path, 'sparse-checkout', 'set', '--no-cone', '--stdin',
            input='\n'.join(PATTERNS) + '\n', stdout=log, stderr=log)
        git(path, 'checkout', branch, stdout=log, stderr=log, timeout=600)
    revision = git(path, 'rev-parse', 'HEAD', capture_output=True).stdout.strip()
    paths = git(path, 'ls-tree', '-r', '--name-only', 'HEAD', capture_output=True).stdout.splitlines()
    record = {'name': name, 'repository': repo, 'url': url, 'branch': branch, 'commit': revision,
              'path': str(path), 'file_count': len(paths), 'audit_only': True}
    (PROJECT / 'reports' / f'{name}-paths.txt').write_text('\n'.join(paths) + '\n')
    print(f'{name}: {revision} ({len(paths)} files indexed)', flush=True)
    return record

BASE.mkdir(exist_ok=True)
records = []
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    futures = {pool.submit(prepare, spec): spec[0] for spec in SPECS}
    for future in concurrent.futures.as_completed(futures):
        try:
            records.append(future.result())
        except Exception as error:
            record = {'name': futures[future], 'error': str(error)}
            records.append(record)
            print(record, flush=True)
(PROJECT / 'reports/audit-sources.json').write_text(json.dumps(records, indent=2))
