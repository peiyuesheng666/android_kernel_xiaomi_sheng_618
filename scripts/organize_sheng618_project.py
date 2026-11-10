#!/usr/bin/env python3
"""Create the standalone sheng project from maintained files and the source cache."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project-root', type=Path, default=Path('/root/sheng-618-project'))
args = parser.parse_args()
workspace = Path(__file__).resolve().parents[1]
template = workspace / 'kernel-project'
project = args.project_root.resolve()
if project.exists():
    raise SystemExit('Destination already exists; choose a new project directory')
inputs = json.loads((template / 'provenance/source-cache.json').read_text())
cache_name = Path(inputs['path']).name
source_archive = template / inputs['path']
if not source_archive.exists():
    source_archive = workspace / 'artifacts/sheng-6.18-release-r70' / cache_name
with source_archive.open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == inputs['sha256']
shutil.copytree(template, project,
                ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', 'logs', 'dist', '*.tar.gz'))
(project / 'assets').mkdir(exist_ok=True)
shutil.copyfile(source_archive, project / inputs['path'])
for path in project.rglob('*'):
    if path.is_file():
        path.chmod(0o755 if path.suffix == '.sh' else 0o644)
        if path.suffix == '.sh':
            subprocess.run(['bash', '-n', path], check=True)
assert (project / 'sheng_defconfig').is_file()
assert not (project / 'profiles/release.config').exists()
for name in ('build.sh', 'buildkernel.sh', 'buildmodules.sh', 'embed.sh', 'mkbootimage.sh'):
    assert (project / name).is_file()
print(json.dumps({'project_root': str(project), 'config': 'sheng_defconfig',
                  'stages': ['buildkernel.sh', 'buildmodules.sh', 'embed.sh', 'mkbootimage.sh'],
                  'source_cache_sha256': inputs['sha256']}, indent=2))
