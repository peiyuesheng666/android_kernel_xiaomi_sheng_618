#!/usr/bin/env python3
"""Reproduce/check the original sheng MetokNLP APK without modifying firmware."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
EXPECTED_APK_SHA = '846c84ea6468d3e3e6e71496ec3ac0fb91760ced00427e7c062e5da01384e8d3'
EXPECTED_LIBRARIES = {
    'lib/arm64-v8a/libapssdk.so': '5b5a21495316fbd20ee04b5a0b515b2912cf3ef98e594a703f4a6ca2b84190c2',
    'lib/arm64-v8a/libmievent.so': 'd404076edc917984b6af87c5013c0e428f5acd9cf3fa18211e1124937ee24d3f',
    'lib/arm64-v8a/libmiui_apssdk.so': '4f8d80089a3bf70b7c0b8fea7e6647e2b740736b210fa04cc5a94d60a18a2918',
    'lib/arm64-v8a/libnlocSDK7d.so': 'c11cf4729458175212cfeca5557092c66844f3d6e332258373645a70915b3e48',
}


def verify(path):
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == EXPECTED_APK_SHA, 'Unexpected MetokNLP APK'
    with zipfile.ZipFile(path) as archive:
        libraries = {info.filename: info for info in archive.infolist()
                     if info.filename.startswith('lib/') and info.filename.endswith('.so')}
        assert set(libraries) == set(EXPECTED_LIBRARIES)
        for name, digest in EXPECTED_LIBRARIES.items():
            assert libraries[name].compress_type == zipfile.ZIP_STORED, name
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest, name
        assert 'AndroidManifest.xml' in archive.namelist() and 'classes.dex' in archive.namelist()
    return len(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-dump', type=Path,
                        help='Read-only extracted partition root, containing product/priv-app/MetokNLP')
    parser.add_argument('--check', action='store_true', help='Only check the already staged APK')
    args = parser.parse_args()
    destination = ROOT / 'proprietary/MetokNLP.apk'
    if not args.check:
        assert args.source_dump, '--source-dump is required for extraction'
        source = args.source_dump.resolve() / 'product/priv-app/MetokNLP/MetokNLP.apk'
        verify(source)
        destination.parent.mkdir(exist_ok=True)
        if destination.exists():
            verify(destination)
        else:
            shutil.copyfile(source, destination)
        assert source.read_bytes() == destination.read_bytes()
    size = verify(destination)
    print(json.dumps({'apk': str(destination), 'sha256': EXPECTED_APK_SHA,
                      'bytes': size, 'original_apk_and_embedded_jni_preserved': True}, indent=2))


if __name__ == '__main__':
    main()
