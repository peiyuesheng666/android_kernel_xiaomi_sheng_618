#!/usr/bin/env python3
"""Restore explicit shallow fetching after an interrupted initial repo sync."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/root/sheng-lineage/lineage-24.0')
LOGS = ROOT.parent / 'logs'
PROJECTS = ('prebuilts/clang/host/linux-x86', 'prebuilts/rust')
TAG = 'refs/tags/android-17.0.0_r1'


def fetch(project):
    gitdir = ROOT / '.repo/projects' / (project + '.git')
    name = project.replace('/', '-')
    log = LOGS / ('shallow-repair-' + name + '.log')
    command = ['git', '-c', 'http.lowSpeedLimit=1024', '-c', 'http.lowSpeedTime=180',
               '--git-dir=' + str(gitdir), 'fetch', '--depth=1', '--no-tags',
               '--no-auto-gc', '--force', '--progress', 'aosp', TAG + ':' + TAG]
    start = time.time()
    with log.open('w') as output:
        code = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT).returncode
    if code == 0:
        commit = subprocess.check_output(['git', '--git-dir=' + str(gitdir),
                                          'rev-parse', TAG + '^{commit}'], text=True).strip()
        shallow = subprocess.check_output(['git', '--git-dir=' + str(gitdir),
                                           'rev-parse', '--is-shallow-repository'], text=True).strip()
        if shallow != 'true':
            raise RuntimeError(project + ' did not become shallow')
    else:
        commit = None
    return {'project': project, 'returncode': code, 'commit': commit,
            'elapsed_seconds': round(time.time() - start), 'log': str(log)}


if __name__ == '__main__':
    # The existing continuation is stopped first; never run two fetches on one Git dir.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(fetch, PROJECTS))
    (LOGS / 'shallow-toolchain-repair.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2), flush=True)
    if any(row['returncode'] for row in results):
        raise SystemExit(1)
