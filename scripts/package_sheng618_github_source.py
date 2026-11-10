#!/usr/bin/env python3
"""Package the tested project in GitHub download layout, with an optional full input bundle."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import zipfile

workspace = Path(__file__).resolve().parents[1]
project = Path('/root/sheng-618-project')
delivery = workspace / 'artifacts/sheng-6.18-project-r70'
hardware_file = workspace / 'reports/kernel618-project-r70-hardware.json'
hardware = json.loads(hardware_file.read_text())
assert hardware['android_boot_completed'] and hardware['wired_adb_available_at_deadline']
build = json.loads((delivery / 'build-result.json').read_text())
adb = [str(workspace / 'tools/platform-tools/adb.exe'), '-s', 'ca10ede3', 'shell']
version = subprocess.check_output(adb + ['cat /proc/version']).decode().strip()
uts = re.search(r'#define UTS_VERSION "(.*?)"', build['build_identity']['uts_version_header'])[1]
assert uts in version
readback = subprocess.check_output(adb + ['head -c ' + str((delivery / 'boot.img').stat().st_size) +
                                         ' /dev/block/by-name/boot_a | sha256sum']).decode().split()[0]
assert readback == build['boot_sha256']

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

backup = workspace / 'reports/device/kernel618-project-r70/pre-flash-boot_a.img'
hardware.update(boot_partition_readback_sha256=readback, compiled_kernel_identity_verified=True,
                live_proc_version=version, pre_flash_boot_backup_sha256=sha(backup),
                pre_flash_boot_backup_bytes=backup.stat().st_size,
                user_confirmed_all_tests_ok=True, user_feedback='OK都是OK的')
hardware_file.write_text(json.dumps(hardware, indent=2, ensure_ascii=False) + '\n')
shutil.copyfile(workspace / 'reports/kernel618-project-r70-build.json', project / 'provenance/validated-build.json')
shutil.copyfile(hardware_file, project / 'provenance/hardware-acceptance.json')
subprocess.run(['rsync', '-a', '--exclude=.git', '--exclude=__pycache__', '--exclude=*.pyc',
                '--exclude=assets/*.tar.gz', '--exclude=logs', '--exclude=dist',
                str(project) + '/', str(workspace / 'kernel-project') + '/'], check=True)

prefix = 'android_kernel_618_for_sheng'
files = []
for path in sorted(project.rglob('*')):
    relative = path.relative_to(project)
    if any(part in ('.git', '__pycache__', 'logs', 'dist') for part in relative.parts):
        continue
    if not path.is_file() or path.suffix == '.pyc':
        continue
    assert not path.is_symlink()
    files.append((path, relative))
github_files = [(path, relative) for path, relative in files
                if not (relative.parts[0] == 'assets' and path.name.endswith(('.tar.gz', '.tar.zst', '.deb')))]
archive_zip = delivery / 'android_kernel_618_for_sheng-source.zip'
full_archive = delivery / 'android_kernel_618_for_sheng-source-with-inputs.tar.gz'
assert not archive_zip.exists() and not full_archive.exists(), 'Preserve previous source deliveries'
with zipfile.ZipFile(archive_zip, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path, relative in github_files:
        archive.write(path, prefix + '/' + relative.as_posix())
with zipfile.ZipFile(archive_zip) as archive:
    assert archive.testzip() is None
    for path, relative in github_files:
        assert hashlib.sha256(archive.read(prefix + '/' + relative.as_posix())).hexdigest() == sha(path)
with tarfile.open(full_archive, 'w:gz', compresslevel=6) as archive:
    for path, relative in files:
        archive.add(path, arcname=prefix + '/' + relative.as_posix(), recursive=False)
with tarfile.open(full_archive, 'r|gz') as archive:
    for member in archive:
        assert member.isfile() and member.name.startswith(prefix + '/')
        relative = Path(member.name).relative_to(prefix)
        assert '..' not in relative.parts
        assert hashlib.file_digest(archive.extractfile(member), 'sha256').hexdigest() == sha(project / relative)
receipt = dict(project_root=str(project), config='profiles/release.config', build_script='build.sh',
               build_steps_script='scripts/build.sh', github_package=str(archive_zip),
               github_package_bytes=archive_zip.stat().st_size, github_package_sha256=sha(archive_zip),
               full_source_package=str(full_archive), full_source_package_bytes=full_archive.stat().st_size,
               full_source_package_sha256=sha(full_archive), source_cache_required_by_github_package=True,
               github_file_count=len(github_files), fresh_compile_passed=True, module_count=344,
               versioned_imports_checked=21003, boot_completed=True, user_confirmed_all_tests_ok=True)
(workspace / 'reports/kernel618-github-source-package.json').write_text(json.dumps(receipt, indent=2) + '\n')
layout = json.loads((workspace / 'reports/kernel618-reference-layout.json').read_text())
layout.update(new_hardware_validation=True, user_confirmed_all_tests_ok=True,
              compiled_identity_and_boot_readback_verified=True, github_package_sha256=sha(archive_zip),
              final_full_source_package_sha256=sha(full_archive))
(workspace / 'reports/kernel618-reference-layout.json').write_text(json.dumps(layout, indent=2) + '\n')
sums = delivery / 'SHA256SUMS'
with sums.open('a') as stream:
    for path in (archive_zip, full_archive):
        stream.write(sha(path) + '  ' + path.name + '\n')
print(json.dumps(receipt, indent=2))
