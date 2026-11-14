#!/usr/bin/env python3
"""Prepare the verified release source snapshot in an independent build root."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

project = Path(os.environ['PROJECT_ROOT']).resolve()
root = Path(os.environ['BUILD_ROOT']).resolve()
marker = root / '.sheng618-ready.json'
inputs = json.loads((project / 'provenance/source-cache.json').read_text())
if marker.exists():
    if json.loads(marker.read_text())['archive_sha256'] != inputs['sha256']:
        raise SystemExit('Build root belongs to a different snapshot; choose a new BUILD_ROOT')
    print('Already prepared: ' + str(root))
    subprocess.run([sys.executable, project / 'scripts/apply-charging-fix.py'], check=True)
    subprocess.run([sys.executable, project / 'scripts/apply-droidspaces-fix.py'], check=True)
    subprocess.run([sys.executable, project / 'scripts/apply-scene-socinfo-fix.py'], check=True)
    subprocess.run([sys.executable, project / 'scripts/apply-pen-release-fix.py'], check=True)
    subprocess.run([sys.executable, project / 'scripts/apply-repair-r85.py'], check=True)
    subprocess.run([sys.executable, project / 'scripts/apply-pen-stability.py'], check=True)
    subprocess.run([sys.executable, project / 'scripts/apply-factory-interfaces.py'], check=True)
    subprocess.run([sys.executable, project / 'scripts/apply-walt-compatibility.py'], check=True)
    raise SystemExit(0)
if root.exists() and any(root.iterdir()):
    raise SystemExit('Unprepared BUILD_ROOT is nonempty; choose an empty directory')
archive = project / inputs['path']
with archive.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
if digest != inputs['sha256']:
    raise SystemExit('Source cache SHA256 mismatch')
root.mkdir(parents=True, exist_ok=True)
with tarfile.open(archive, 'r|gz') as stream:
    prefix = inputs['prefix'] + '/k618/'
    for member in stream:
        if not member.name.startswith(prefix):
            continue
        relative = Path(member.name[len(inputs['prefix']) + 1:])
        if relative.is_absolute() or '..' in relative.parts:
            raise SystemExit('Invalid source cache path: ' + member.name)
        member.name = relative.as_posix()
        if member.islnk():
            if not member.linkname.startswith(prefix):
                raise SystemExit('Escaping source hardlink')
            member.linkname = member.linkname[len(inputs['prefix']) + 1:]
        stream.extract(member, path=root, filter='data')
subprocess.run([sys.executable, project / 'scripts/relocate-inputs.py', root], check=True)
expected = json.loads((project / 'provenance/source-files.json').read_text())
for name, want in expected.items():
    with (root / name).open('rb') as stream:
        got = hashlib.file_digest(stream, 'sha256').hexdigest()
    if got != want:
        raise SystemExit('Source mismatch: ' + name)
for path in (root / 'k618').rglob('*'):
    if path.is_symlink() and not path.resolve().is_relative_to(root):
        raise SystemExit('Escaping source symlink: ' + str(path))
subprocess.run([sys.executable, project / 'scripts/apply-charging-fix.py'], check=True)
subprocess.run([sys.executable, project / 'scripts/apply-droidspaces-fix.py'], check=True)
subprocess.run([sys.executable, project / 'scripts/apply-scene-socinfo-fix.py'], check=True)
subprocess.run([sys.executable, project / 'scripts/apply-pen-release-fix.py'], check=True)
subprocess.run([sys.executable, project / 'scripts/apply-repair-r85.py'], check=True)
subprocess.run([sys.executable, project / 'scripts/apply-pen-stability.py'], check=True)
subprocess.run([sys.executable, project / 'scripts/apply-factory-interfaces.py'], check=True)
subprocess.run([sys.executable, project / 'scripts/apply-walt-compatibility.py'], check=True)
marker.write_text(json.dumps({'archive_sha256': digest, 'source_files': len(expected)}, indent=2) + '\n')
print('Prepared and hash-verified ' + str(len(expected)) + ' source files: ' + str(root / 'k618'))
