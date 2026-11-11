#!/usr/bin/env python3
"""Preserve the verified r85 checkpoint and isolate its r76-based successor."""
from pathlib import Path
import json
import shutil
import subprocess

workspace=Path(__file__).resolve().parents[1]
base_project=Path('/root/sheng-618-repair-r85-project')
base_build=Path('/root/sheng-618-repair-r85-build')
project=Path('/root/sheng-618-repair-r86-project')
build=Path('/root/sheng-618-repair-r86-build')
checkpoint=json.loads((workspace/'artifacts/sheng-6.18-repair-r85/package-validation.json').read_text())
assert checkpoint['patch_replay_verified'] and checkpoint['archive_readback_verified']
assert not project.exists() and not build.exists()
print('Copying verified r85 into independent r86 project/build',flush=True)
shutil.copytree(base_project,project,symlinks=True,
    ignore=shutil.ignore_patterns('.git','dist','logs','__pycache__','*.pyc'))
subprocess.run(['cp','-a','--reflink=auto',str(base_build),str(build)],check=True)
for path in build.rglob('*'):
    if path.is_symlink():
        target=str(path.readlink())
        if target.startswith(str(base_build)+'/'):
            path.unlink();path.symlink_to(target.replace(str(base_build)+'/',str(build)+'/',1))
path=project/'scripts/project-env.sh';text=path.read_text()
text=text.replace(str(base_build),str(build)).replace('sheng-618-repair-r85-build','sheng-618-repair-r86-build')
text=text.replace('TAG="${TAG:-repair-r85}"','TAG="${TAG:-repair-r86}"')
path.write_text(text)
print('Independent r86 checkout ready; r85 source and delivery preserved',flush=True)
