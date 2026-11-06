#!/usr/bin/env python3
"""Reduce four task-owned prebuilt Git caches without removing checkout files."""
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from build_events import probe

ROOT = Path('/root/sheng-lineage/lineage-24.0')
LOGS = ROOT.parent / 'logs'
PROJECTS = ('prebuilts/sdk', 'prebuilts/module_sdk/art',
            'prebuilts/remoteexecution-client', 'prebuilts/misc')
TAG = 'refs/tags/android-17.0.0_r1'


def size(directory):
    return int(subprocess.check_output(['du', '-s', '--block-size=1', str(directory)], text=True).split()[0])


def main():
    assert (LOGS / 'source-maintenance.pending').is_file()
    assert probe(LOGS)['state'] != 'running', 'Do not repack caches while a build runs'
    assert (LOGS / 'rom-status.txt').read_text().strip() == 'synced'
    projects = ET.parse(LOGS / 'source-manifest.xml').getroot().findall('project')
    report = {'checkout_files_removed': 0, 'projects': []}
    for relative in PROJECTS:
        matches = [p for p in projects if p.get('path', p.get('name')) == relative]
        assert len(matches) == 1
        name = matches[0].get('name')
        assert sum(p.get('name') == name for p in projects) == 1, 'Shared object repository must be handled separately'
        gitdir = ROOT / '.repo/projects' / (relative + '.git')
        objects = (gitdir / 'objects').resolve()
        expected = (ROOT / '.repo/project-objects' / (name + '.git') / 'objects').resolve()
        assert objects == expected and objects.is_relative_to(ROOT / '.repo/project-objects')
        git = ['git', '--git-dir=' + str(gitdir), '--work-tree=' + str(ROOT / relative)]
        def output(*args):
            return subprocess.check_output(git + list(args), text=True).strip()
        commit = output('rev-parse', 'HEAD^{commit}')
        assert output('rev-parse', TAG + '^{commit}') == commit
        refs = output('for-each-ref', '--format=%(refname)').splitlines()
        assert refs
        # Never discard a different branch, tag, or a user's edits.
        assert all(output('rev-parse', ref + '^{commit}') == commit for ref in refs), relative + ': additional revisions need review'
        assert not output('status', '--porcelain', '--untracked-files=no'), relative + ': tracked edits exist'
        row = {'path': relative, 'commit': commit, 'refs': refs, 'before_bytes': size(objects)}
        log = LOGS / ('slim-' + relative.replace('/', '-') + '.log')
        with log.open('w') as stream:
            def run(*args):
                subprocess.run(git + list(args), stdout=stream, stderr=subprocess.STDOUT, check=True)
            run('-c', 'http.lowSpeedLimit=1024', '-c', 'http.lowSpeedTime=180',
                'fetch', '--depth=1', '--no-tags', '--no-auto-gc', '--force', 'aosp', TAG + ':' + TAG)
            assert output('rev-parse', '--is-shallow-repository') == 'true'
            run('reflog', 'expire', '--expire=now', '--all')
            run('-c', 'pack.threads=4', 'repack', '-ad')
            run('prune', '--expire=now')
            run('fsck', '--connectivity-only', '--no-reflogs')
        assert output('rev-parse', 'HEAD^{commit}') == commit
        assert not output('status', '--porcelain', '--untracked-files=no')
        row.update(after_bytes=size(objects), shallow=True, connectivity_checked=True,
                   checkout_unchanged=True, log=str(log))
        report['projects'].append(row)
        report['reclaimed_bytes'] = sum(p['before_bytes'] - p['after_bytes'] for p in report['projects'])
        (LOGS / 'source-cache-slimming.json').write_text(json.dumps(report, indent=2) + '\n')
        print(f'{relative}: {row["before_bytes"] / 1024**3:.2f} -> {row["after_bytes"] / 1024**3:.2f} GiB', flush=True)


if __name__ == '__main__':
    main()
