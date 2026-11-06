#!/usr/bin/env python3
"""Export verified build outputs without host paths, signing keys or source links."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile

PROJECT = Path(__file__).resolve().parents[1]
DIST = Path('/root/sheng-612/out/ack-dist')
report = json.loads((PROJECT / 'reports/build-result.json').read_text())
assert report['status'] == 'compiled-and-checked'
assert report['device_ready'] is False
release = report['release']
output = PROJECT / 'artifacts' / f'{release}-baseline.tar.gz'
output.parent.mkdir(exist_ok=True)
files = [p for p in DIST.rglob('*') if p.is_file() and not p.is_symlink()]
note = f'''Google ACK ARM64 baseline: {release}

This archive contains a compiled upstream ACK baseline and its GKI modules.
It is NOT a sheng boot package and has NOT been boot-tested on a device.
Original 5.15 vendor modules cannot be used with this 6.12 kernel.
The SM8550/Kalama BSP, sheng drivers and matching DTBs/modules still need migration.

ACK source commit: {report['ack_commit']}
See build-result.json for checksums, build method and validation scope.
'''.encode()
with tarfile.open(output, 'w:gz') as tf:
    entry = tarfile.TarInfo('README.txt')
    entry.size = len(note)
    entry.mode = 0o644
    tf.addfile(entry, io.BytesIO(note))
    for file in sorted(files):
        relative = file.relative_to(DIST)
        if any(part in ('build', 'source') for part in relative.parts):
            continue
        tf.add(file, arcname=str(relative), recursive=False)
    for name in ('toolchains.json', 'source-probe.json', 'stock-boot.json'):
        tf.add(PROJECT / 'reports' / name, arcname=f'provenance/{name}', recursive=False)
with tarfile.open(output) as tf:
    names = tf.getnames()
    assert 'Image' in names and 'Image.gz' in names and 'build-result.json' in names
    assert not any(member.issym() or member.islnk() for member in tf.getmembers())
digest = hashlib.sha256(output.read_bytes()).hexdigest()
output.with_suffix(output.suffix + '.sha256').write_text(f'{digest}  {output.name}\n')
report['export'] = {'path': str(output), 'bytes': output.stat().st_size, 'sha256': digest}
(PROJECT / 'reports/build-result.json').write_text(json.dumps(report, indent=2))
Path('/root/sheng-612/logs/build-status.txt').write_text('complete\n')
print(f'Exported {output.name}: {output.stat().st_size // 1048576} MiB; sha256 {digest}')
