#!/usr/bin/env python3
"""Remove expired sheng image-packaging scratch copies, keeping small logs.

The fixed cutoff excludes every new batch. Source, release artifacts and ROM
build outputs are outside the only permitted root. Preview unless --delete.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

ROOT = Path('/root/sheng-lineage/hardware-followup')
CUTOFF = '20261107T040000000000Z'
NAME = re.compile(r'(\d{8}T\d{12}Z)(?:-(?:model|location|overlay))?')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--delete', action='store_true')
    args = parser.parse_args()
    assert ROOT.resolve() == ROOT and ROOT.is_dir() and not ROOT.is_symlink()
    for process in Path('/proc').iterdir():
        if process.name.isdecimal():
            try:
                command = (process / 'cmdline').read_bytes().replace(b'\0', b' ')
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
            assert not re.search(rb'python\S* .*package_sheng_\w+\.py', command), \
                'A packaging process is running; do not remove scratch copies'
    candidates = []
    for directory in sorted(ROOT.iterdir()):
        match = NAME.fullmatch(directory.name)
        if not match or match[1] >= CUTOFF:
            continue
        assert directory.is_dir() and not directory.is_symlink()
        assert directory.resolve().parent == ROOT
        size = sum(p.lstat().st_blocks * 512 for p in directory.rglob('*'))
        candidates.append((directory, size))
    report = {'date_utc': datetime.now(timezone.utc).isoformat(), 'root': str(ROOT),
              'cutoff_exclusive': CUTOFF, 'delete_requested': args.delete,
              'directories': [{'path': str(p), 'allocated_bytes': n} for p, n in candidates],
              'allocated_bytes_total': sum(n for _, n in candidates)}
    if args.delete:
        archive = Path('/root/sheng-lineage/logs') / datetime.now(timezone.utc).strftime('staging-cleanup-%Y%m%dT%H%M%SZ')
        archive.mkdir()
        for directory, _ in candidates:
            # Recheck resolved deletion targets immediately before the mutation.
            assert directory.resolve().parent == ROOT and not directory.is_symlink()
            evidence = [p for p in directory.iterdir() if p.is_file() and not p.is_symlink()
                        and p.suffix in ('.json', '.txt', '.log', '.debugfs')
                        and p.stat().st_size <= 1024 * 1024]
            if evidence:
                saved = archive / directory.name
                saved.mkdir()
                for source in evidence:
                    shutil.copy2(source, saved / source.name)
            shutil.rmtree(directory)
            assert not directory.exists()
        report['small_log_archive'] = str(archive)
        report['deleted'] = True
        (archive / 'cleanup-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
