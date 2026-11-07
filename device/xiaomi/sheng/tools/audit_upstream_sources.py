#!/usr/bin/env python3
"""Fresh-fetch public sources and verify the pinned commit and tracked files.

Only remote refs and the selected report are written. No checkout, reset,
clean, source patching or untracked-file deletion is performed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from datetime import datetime, timezone

OWNED_PUBLIC_REPOS = [
    'frameworks/base', 'frameworks/native', 'frameworks/av',
    'packages/apps/Settings', 'system/sepolicy', 'hardware/xiaomi',
    'hardware/qcom-caf/sm8550/display',
    'hardware/qcom-caf/sm8550/audio/pal',
    'hardware/qcom-caf/sm8550/audio/graphservices',
    'hardware/qcom-caf/sm8550/audio/primary-hal',
    'kernel/xiaomi/sm8550', 'kernel/xiaomi/sm8550-modules',
    'kernel/xiaomi/sm8550-devicetrees',
    'vendor/qcom/opensource/healthd-ext',
]

def run(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *args],
                          capture_output=True, check=check)

def inspect(rom, relative, fetch):
    repo = rom/relative
    head = run(repo, 'rev-parse', 'HEAD').stdout.decode().strip()
    origin = run(repo, 'remote', 'get-url', 'origin', check=False)
    remote = 'origin' if origin.returncode == 0 else run(repo, 'remote').stdout.decode().splitlines()[0]
    url = run(repo, 'remote', 'get-url', remote).stdout.decode().strip()
    fetched = None
    if fetch:
        # Fetch the exact pinned revision again from its upstream. Updating to
        # a different branch tip would change this ROM's manifest baseline.
        result = run(repo, 'fetch', '--no-tags', remote, head, check=False)
        fetched = {'returncode': result.returncode,
                   'output': (result.stdout+result.stderr).decode(errors='replace').strip()}
        if result.returncode:
            return {'path': relative, 'remote': url, 'head': head, 'fetch': fetched, 'passed': False}
        fetched_head = run(repo, 'rev-parse', 'FETCH_HEAD').stdout.decode().strip()
    else:
        fetched_head = None
    diff = run(repo, 'diff', '--binary', 'HEAD', '--').stdout
    staged = run(repo, 'diff', '--cached', '--binary', 'HEAD', '--').stdout
    untracked = run(repo, 'ls-files', '--others', '--exclude-standard').stdout.decode(errors='replace').splitlines()
    status = run(repo, 'status', '--porcelain=v1').stdout.decode(errors='replace').strip()
    # Check physical bytes against upstream blob IDs as well. This does not
    # rely on Git's worktree stat cache or assume-unchanged index flags.
    mismatches = []
    tracked_count = 0
    for entry in run(repo, 'ls-tree', '-r', '-z', head).stdout.split(b'\0'):
        if not entry:
            continue
        meta, filename = entry.split(b'\t', 1)
        mode, kind, expected = meta.split()
        if kind != b'blob':
            continue
        tracked_count += 1
        path = repo/os.fsdecode(filename)
        if not path.exists() and not path.is_symlink():
            mismatches.append({'file': os.fsdecode(filename), 'reason': 'missing'})
            continue
        info = path.lstat()
        if mode == b'120000':
            data = os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes()
            digest = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            mode_ok = path.is_symlink()
        else:
            digest_obj = hashlib.sha1(b'blob '+str(info.st_size).encode()+b'\0')
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024*1024), b''):
                    digest_obj.update(block)
            digest = digest_obj.hexdigest()
            mode_ok = stat.S_ISREG(info.st_mode) and bool(info.st_mode & 0o111) == (mode == b'100755')
        if digest != expected.decode() or not mode_ok:
            mismatches.append({'file': os.fsdecode(filename), 'expected_blob': expected.decode(),
                               'actual_blob': digest, 'mode_matches': mode_ok})
    return {'path': relative, 'remote': url, 'head': head,
            'tree': run(repo, 'rev-parse', 'HEAD^{tree}').stdout.decode().strip(),
            'fetch': fetched, 'fetched_head': fetched_head,
            'tracked_diff_bytes': len(diff), 'staged_diff_bytes': len(staged),
            'tracked_diff_sha256': hashlib.sha256(diff).hexdigest(),
            'untracked_files': untracked, 'status': status,
            'tracked_files_byte_verified': tracked_count, 'physical_file_mismatches': mismatches,
            'passed': not diff and not staged and not untracked and not mismatches and
                      (not fetch or fetched_head == head)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rom', type=Path, default=Path('/root/sheng-lineage/lineage-24.0'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda p: inspect(args.rom, p, args.fetch), OWNED_PUBLIC_REPOS))
    # Audit every repo-managed project as well, so a missed source edit cannot
    # hide behind the known list. Generated vendor/device inputs are listed.
    projects = (args.rom/'.repo/project.list').read_text().splitlines()
    def status(relative):
        r = run(args.rom/relative, 'status', '--porcelain=v1', check=False)
        return {'path': relative, 'returncode': r.returncode,
                'status': r.stdout.decode(errors='replace').strip()}
    with ThreadPoolExecutor(max_workers=8) as executor:
        all_status = list(executor.map(status, projects))
    dirty = [r for r in all_status if r['status'] or r['returncode']]
    report = {'date_utc': datetime.now(timezone.utc).isoformat(),
              'comparison': 'Fresh upstream exact revision pinned by the current manifest; branch tips are not substituted.',
              'repositories': results, 'project_count': len(projects),
              'all_project_nonclean_status': dirty,
              'known_public_sources_passed': all(r['passed'] for r in results)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    raise SystemExit(0 if report['known_public_sources_passed'] and not dirty else 1)

if __name__ == '__main__':
    main()
