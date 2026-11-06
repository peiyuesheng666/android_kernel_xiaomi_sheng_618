#!/usr/bin/env python3
"""Check production APK inputs; retain intentionally malformed test fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--require-clean', action='store_true')
args = parser.parse_args()
work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
paths = subprocess.check_output(['rg', '--files', '--hidden', '--no-ignore', '-g', '!out/**',
    '-g', '!.repo/**', '-g', '!**/.git/**', '-g', '*.apk'], cwd=rom, text=True).splitlines()
excluded = re.compile(r'(^|/)(?:tests?|testdata|testcases|test_data|test-apps|testing|fixtures?|offline_files|cts|vts|samples?|fuzz)(/|$)', re.I)
checked, skipped, errors = [], [], []
for relative in sorted(set(paths)):
    if excluded.search(relative) or (relative.startswith('external/chromium-webview/prebuilt/')
                                    and not relative.startswith('external/chromium-webview/prebuilt/arm64/')):
        skipped.append(relative)
        continue
    file = rom / relative
    with file.open('rb') as stream:
        prefix = stream.read(160)
    if prefix.startswith(b'version https://git-lfs.github.com/spec/v1'):
        errors.append({'file': relative, 'error': 'unmaterialized Git LFS pointer'})
        continue
    try:
        with zipfile.ZipFile(file) as archive:
            assert sum(item.file_size for item in archive.infolist()) < 5 * 1024**3, 'Unexpectedly large APK expansion'
            assert 'AndroidManifest.xml' in archive.namelist(), 'Missing AndroidManifest.xml'
            broken = archive.testzip()
            assert broken is None, 'CRC failure: ' + str(broken)
        checked.append({'file': relative, 'bytes': file.stat().st_size})
    except (zipfile.BadZipFile, AssertionError, RuntimeError, OSError) as error:
        errors.append({'file': relative, 'error': str(error)})
webview = rom / 'external/chromium-webview/prebuilt/arm64'
pointer_size = int(subprocess.check_output(['git', '-C', str(webview), 'cat-file', '-s', 'HEAD:webview.apk'], text=True))
lfs_verified = False
if pointer_size < 1024:
    pointer = subprocess.check_output(['git', '-C', str(webview), 'show', 'HEAD:webview.apk'], text=True)
    match = re.fullmatch(r'version https://git-lfs.github.com/spec/v1\noid sha256:([a-f0-9]{64})\nsize (\d+)\n', pointer)
    assert match, 'Unexpected WebView LFS pointer format'
    digest = hashlib.sha256()
    with (webview / 'webview.apk').open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    lfs_verified = digest.hexdigest() == match[1] and (webview / 'webview.apk').stat().st_size == int(match[2])
    if not lfs_verified:
        errors.append({'file': 'external/chromium-webview/prebuilt/arm64/webview.apk', 'error': 'LFS SHA256/size mismatch'})
report = {'production_apks_checked': len(checked), 'checked': checked, 'errors': errors,
          'skipped_test_or_other_architecture_apks': skipped, 'webview_lfs_oid_verified': lfs_verified,
          'all_passed': not errors, 'rom_compiled': False}
(work / 'reports/prebuilt-apk-integrity.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: report[key] for key in ('production_apks_checked', 'webview_lfs_oid_verified', 'all_passed', 'errors')}, indent=2))
if args.require_clean and errors:
    raise SystemExit(1)
