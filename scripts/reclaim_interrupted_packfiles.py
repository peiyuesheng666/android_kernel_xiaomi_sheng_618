#!/usr/bin/env python3
"""Remove only four named, abandoned temporary downloads from this task."""
import json
from pathlib import Path

root = Path('/root/sheng-lineage/lineage-24.0/.repo/project-objects').resolve()
names = (
    'platform/prebuilts/clang/host/linux-x86.git/objects/pack/tmp_pack_e4FfBQ',
    'platform/prebuilts/clang/host/linux-x86.git/objects/pack/tmp_pack_ompIZu',
    'platform/prebuilts/rust.git/objects/pack/tmp_pack_jftp2n',
    'platform/prebuilts/rust.git/objects/pack/tmp_pack_lfpgDQ',
)
files = [(root / name).resolve() for name in names]
for file in files:
    assert file.is_relative_to(root) and file.name.startswith('tmp_pack_')
    assert file.is_file() and not file.is_symlink()
inodes = {(file.stat().st_dev, file.stat().st_ino) for file in files}
for process in Path('/proc').iterdir():
    if not process.name.isdigit():
        continue
    try:
        handles = list((process / 'fd').iterdir())
    except FileNotFoundError:
        continue
    for handle in handles:
        try:
            stat = handle.stat()
        except (FileNotFoundError, ProcessLookupError):
            continue
        assert (stat.st_dev, stat.st_ino) not in inodes, f'File still open: {handle}'
report = [{'path': str(file), 'bytes': file.stat().st_size} for file in files]
for file in files:
    file.unlink()
Path('/root/sheng-lineage/logs/reclaimed-interrupted-packs.json').write_text(json.dumps(report, indent=2) + '\n')
print(f'Reclaimed {sum(row["bytes"] for row in report) / 1024**3:.2f} GiB of abandoned, non-resumable temporary packs')
