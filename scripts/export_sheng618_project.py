#!/usr/bin/env python3
"""Export the organized project and its verified build to the delivery folder."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

workspace = Path(__file__).resolve().parents[1]
project = Path('/root/sheng-618-project')
build = Path('/root/sheng-618-project-build/k618/out-gki')
validation = json.loads((project / 'dist/release-r70/validation.json').read_text())
assert validation['fresh_build_verified'] and validation['module_abi']['abi_passed']
dest = workspace / 'artifacts/sheng-6.18-project-r70'
dest.mkdir(exist_ok=True)
for name in ('Image', 'boot.img'):
    shutil.copyfile(project / 'dist/release-r70' / name, dest / name)

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

compiled = json.loads((build / 'build-result.json').read_text())
config = (build / '.config').read_text()
assert not any(line.endswith(('=y', '=m')) for line in config.splitlines()
               if line.startswith(('CONFIG_KSU', 'CONFIG_SUSFS', 'CONFIG_SHENG_BOOTLOG')))
receipt = json.loads((workspace / 'artifacts/sheng-6.18-release-r70/build-result.json').read_text())
receipt.update(revision='project-r70', boot_sha256=sha(dest / 'boot.img'), image_sha256=sha(dest / 'Image'),
               build_type='release', test_timeout_seconds=None, fresh_build_verified=True,
               source_project=str(project), source_build_root=str(build.parent),
               build_log=str(project / 'logs/release-r70/build.log'),
               kernel_config_sha256=sha(build / '.config'),
               module_overlay=str(build / 'overlay.cpio'), module_overlay_sha256=sha(build / 'overlay.cpio'),
               organized_build=compiled, module_abi=validation['module_abi'])
receipt['build_identity']['release'] = compiled['release']
receipt['build_identity']['compile_header'] = (build / 'include/generated/compile.h').read_text()
receipt['build_identity']['uts_version_header'] = (build / 'include/generated/utsversion.h').read_text()
(dest / 'build-result.json').write_text(json.dumps(receipt, indent=2) + '\n')
shutil.copyfile(build / '.config', dest / 'kernel.config')
shutil.copyfile(project / 'dist/release-r70/validation.json', workspace / 'reports/kernel618-project-r70-build.json')
subprocess.run(['rsync', '-a', '--exclude=.git', '--exclude=__pycache__', '--exclude=*.pyc',
                '--exclude=assets/*.tar.gz', '--exclude=logs', '--exclude=dist',
                str(project) + '/', str(workspace / 'kernel-project') + '/'], check=True)
archive = dest / 'sheng-6.18.32-project-r70-source.tar.gz'
assert not archive.exists(), 'Preserve existing delivery archives'
subprocess.run(['tar', '-czf', archive, '--exclude=.git', '--exclude=__pycache__',
                '--exclude=*.pyc', '--exclude=logs', '--exclude=dist', '-C', project.parent, project.name], check=True)
with tarfile.open(archive, 'r|gz') as stream:
    entries = 0
    for member in stream:
        assert member.name == project.name or member.name.startswith(project.name + '/')
        assert '..' not in Path(member.name).parts and not Path(member.name).is_absolute()
        if member.isfile():
            live = project.parent / member.name
            assert hashlib.file_digest(stream.extractfile(member), 'sha256').hexdigest() == sha(live), member.name
            entries += 1
files = ['boot.img', 'Image', archive.name]
(dest / 'SHA256SUMS').write_text(''.join(sha(dest / name) + '  ' + name + '\n' for name in files))
layout = json.loads((workspace / 'reports/kernel618-reference-layout.json').read_text())
layout.update(fresh_build_verified=True, module_abi_passed=True, source_archive=str(archive),
              source_archive_sha256=sha(archive), source_archive_files_verified=entries,
              shared_inputs='/root/sheng-source-inputs', retired_kernel612_removed=True,
              portable_ps5169_include=True)
(workspace / 'reports/kernel618-reference-layout.json').write_text(json.dumps(layout, indent=2) + '\n')
print(json.dumps({'delivery': str(dest), 'boot_sha256': receipt['boot_sha256'],
                  'source_archive_sha256': sha(archive), 'files_verified': entries}, indent=2))
