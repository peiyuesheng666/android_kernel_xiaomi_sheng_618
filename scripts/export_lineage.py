#!/usr/bin/env python3
"""Export successful sheng artifacts with hashes; never report a hardware boot."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import zipfile

root = Path('/root/sheng-lineage')
product = root / 'lineage-24.0/out/target/product/sheng'
assert (root / 'logs/build-status.txt').read_text().strip() == 'compiled'
zips = sorted(product.glob('lineage-*-sheng.zip'), key=lambda p: p.stat().st_mtime)
assert zips, 'No completed ROM zip found'
with zipfile.ZipFile(zips[-1]) as archive:
    assert 'payload.bin' in archive.namelist(), 'Expected A/B OTA payload'
    assert archive.testzip() is None, 'Corrupt ROM zip'
dest = Path(__file__).resolve().parents[1] / 'artifacts' / zips[-1].stem
dest.mkdir(parents=True, exist_ok=True)
files = [zips[-1]]
for name in ('boot.img', 'vendor_boot.img', 'init_boot.img', 'recovery.img', 'dtbo.img', 'vbmeta.img', 'vbmeta_system.img'):
    source = product / name
    assert source.is_file(), f'Missing required image {name}'
    files.append(source)
abi_report = product / 'obj/KERNEL_OBJ/sheng-stock-module-compatibility.json'
assert abi_report.is_file(), 'Stock board module compatibility check was not run'
abi = json.loads(abi_report.read_text())
expected_modules = json.loads((Path(__file__).resolve().parents[1] / 'reports/sheng-stock-preparation.json').read_text())['prepared_module_names']
assert not abi['errors'] and sorted(abi['modules']) == expected_modules
report = {'compiled': True, 'hardware_boot_tested': False, 'board_module_abi': abi, 'files': []}
checksums = []
# A pinned manifest does not describe uncommitted BSP changes.
workspace = Path(__file__).resolve().parents[1]
report['source_patches'] = []
for patch in sorted((workspace / 'patches').glob('*.patch')):
    relative = Path('source-patches') / patch.name
    target = dest / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(patch, target)
    digest = hashlib.sha256(patch.read_bytes()).hexdigest()
    checksums.append(f'{digest}  {relative.as_posix()}')
    report['source_patches'].append({'name': relative.as_posix(), 'sha256': digest})
configuration = dest / 'sheng-build-configuration.tar.gz'
with tarfile.open(configuration, 'w:gz') as archive:
    for directory in ('device/xiaomi/sheng', 'manifests', 'patches', 'scripts'):
        for file in sorted((workspace / directory).rglob('*')):
            if not file.is_file() or {'.git', '__pycache__'} & set(file.parts):
                continue
            if directory == 'scripts' and file.suffix not in ('.py', '.sh', '.ps1'):
                continue
            archive.add(file, arcname=str(file.relative_to(workspace)), recursive=False)
configuration_sha = hashlib.sha256(configuration.read_bytes()).hexdigest()
checksums.append(f'{configuration_sha}  {configuration.name}')
report['configuration_snapshot'] = {'name': configuration.name, 'sha256': configuration_sha,
                                     'bytes': configuration.stat().st_size}
manifest = dest / 'source-manifest.xml'
shutil.copyfile(root / 'logs/source-manifest.xml', manifest)
manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
checksums.append(f'{manifest_sha}  {manifest.name}')
report['source_manifest_sha256'] = manifest_sha
for source in files:
    sha = hashlib.sha256()
    with source.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            sha.update(block)
    digest = sha.hexdigest()
    shutil.copyfile(source, dest / source.name)
    checksums.append(f'{digest}  {source.name}')
    report['files'].append({'name': source.name, 'bytes': source.stat().st_size, 'sha256': digest})
(dest / 'SHA256SUMS').write_text('\n'.join(checksums) + '\n')
(dest / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
print(f'Successful build artifacts exported to {dest}; hardware testing is still pending')
