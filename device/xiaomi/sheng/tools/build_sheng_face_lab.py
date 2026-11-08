#!/usr/bin/env python3
"""Build the source-owned face capture lab without regenerating the ROM graph.

Does not install/launch the app, open a camera, modify a ROM image or flash.
Requires fresh, byte-verified upstream and toolchain receipts from this checkout.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import xml.etree.ElementTree as ET
import zipfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rom', type=Path, default=Path('/root/sheng-lineage/lineage-24.0'))
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    rom, work = args.rom.resolve(), args.work.resolve()
    source = rom/'device/xiaomi/sheng/interfaces/biometrics/softwareface'
    work.mkdir(parents=True, exist_ok=True)
    audit = work/'upstream-preaudit.json'
    toolaudit = work/'toolchain-preaudit.json'
    report = json.loads(audit.read_text())
    tools = json.loads(toolaudit.read_text())
    assert report['known_public_sources_passed'] and not report['all_project_nonclean_status']
    assert datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(report['date_utc']).timestamp() < 7200
    assert len(tools) == 3 and all(x['passed'] and x['fetched_head'] == x['head'] for x in tools)
    for entry in tools:
        actual = subprocess.check_output(['git', '-C', str(rom/entry['path']), 'rev-parse', 'HEAD'], text=True).strip()
        assert actual == entry['head']
    assert not [p for p in source.rglob('*') if p.suffix in ('.so', '.jar', '.tflite', '.onnx', '.pb')]
    manifest = ET.parse(source/'AndroidManifest.xml').getroot()
    android = '{http://schemas.android.com/apk/res/android}'
    assert [x.get(android+'name') for x in manifest.findall('uses-permission')] == ['android.permission.CAMERA']
    application = manifest.find('application')
    assert application.get(android+'allowBackup') == 'false'
    assert application.find('service') is None and application.find('receiver') is None

    java_home = rom/'prebuilts/jdk/jdk21/linux-x86'
    java = java_home/'bin/java'
    javac = java_home/'bin/javac'
    sdk = rom/'prebuilts/sdk/37.0/public/android.jar'
    lambda_stubs = rom/'prebuilts/sdk/tools/core-lambda-stubs.jar'
    aapt = rom/'out/host/linux-x86/bin/aapt2'
    r8 = rom/'prebuilts/r8/r8.jar'
    signer = rom/'out/host/linux-x86/framework/apksigner.jar'
    # Fresh output directories keep stale classes/dex out of the APK. Existing builds are retained.
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    build = work/run_id
    build.mkdir()
    classes, dex, host = (build/n for n in ('classes', 'dex', 'host-tests'))
    for directory in (classes, dex, host):
        directory.mkdir()
    commands = []
    log = build/'build.log'

    def run(command):
        command = [str(x) for x in command]
        commands.append(command)
        completed = subprocess.run(command, cwd=build, capture_output=True, text=True,
                                   encoding='utf-8', errors='replace',
                                   env={**os.environ, 'LC_ALL': 'C.UTF-8'})
        with log.open('a') as stream:
            stream.write(json.dumps(command)+'\n'+completed.stdout+completed.stderr+'\n')
        if completed.returncode:
            raise RuntimeError(f'Command failed ({completed.returncode}): {command[0]}\n{completed.stdout}{completed.stderr}')
        return completed.stdout + completed.stderr

    package = source/'src/org/lineageos/sheng/facelab'
    core = [package/n for n in ('FrameMath.java', 'FaceDescriptor.java', 'SampleCollector.java')]
    run([javac, '--release', '11', '-encoding', 'UTF-8', '-d', host, *core, source/'tests/CoreTests.java'])
    tests = run([java, '-cp', host, 'org.lineageos.sheng.facelab.CoreTests']).strip()
    run([javac, '-source', '8', '-target', '8', '-encoding', 'UTF-8',
         '-bootclasspath', str(lambda_stubs)+os.pathsep+str(sdk),
         '-d', classes, *sorted((source/'src').rglob('*.java'))])
    classjar = build/'classes.jar'
    with zipfile.ZipFile(classjar, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(classes.rglob('*.class')):
            archive.write(path, path.relative_to(classes).as_posix())
    run([java, '-cp', r8, 'com.android.tools.r8.D8', '--release', '--min-api', '30',
         '--lib', sdk, '--output', dex, classjar])
    resources = build/'resources.apk'
    run([aapt, 'link', '-I', sdk, '--manifest', source/'AndroidManifest.xml', '-o', resources])
    unsigned = build/'ShengFaceLab-unsigned.apk'
    with zipfile.ZipFile(resources) as inputs, zipfile.ZipFile(unsigned, 'w', zipfile.ZIP_DEFLATED) as archive:
        for entry in inputs.infolist():
            archive.writestr(entry, inputs.read(entry))
        for path in sorted(dex.glob('*.dex')):
            archive.write(path, path.name)

    key = work/'lab-signing.p12'
    password = work/'lab-signing-password.txt'
    if not key.exists():
        assert not password.exists(), 'Inspect incomplete prior key generation before retrying'
        password.write_text(secrets.token_hex(24)+'\n')
        os.chmod(password, 0o600)
        run([java_home/'bin/keytool', '-genkeypair', '-keystore', key, '-storetype', 'PKCS12',
             '-alias', 'shengfacelab', '-keyalg', 'RSA', '-keysize', '3072', '-validity', '3650',
             '-dname', 'CN=ShengFaceLab Development', '-storepass:file', password])
        os.chmod(key, 0o600)
    apk = build/'ShengFaceLab.apk'
    run([java, '-jar', signer, 'sign', '--ks', key, '--ks-key-alias', 'shengfacelab',
         '--ks-pass', 'file:'+str(password), '--out', apk, unsigned])
    signature = run([java, '-jar', signer, 'verify', '--verbose', '--print-certs', apk])
    badging = run([aapt, 'dump', 'badging', apk])
    with zipfile.ZipFile(apk) as archive:
        assert 'classes.dex' in archive.namelist()
        assert not any(x.startswith('lib/') for x in archive.namelist())
    inputs = [*sorted(source.rglob('*.java')), source/'AndroidManifest.xml', source/'Android.bp',
              Path(__file__).resolve()]
    receipt = {
        'date_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'development capture/comparison APK; not a face HAL or accepted repair',
        'product_registered': False, 'device_installed': False, 'camera_opened': False,
        'raw_images_persisted': False, 'authentication_decision_implemented': False,
        'core_tests': tests, 'apk': str(apk), 'apk_bytes': apk.stat().st_size,
        'apk_sha256': digest(apk), 'signature_verification': signature,
        'badging': badging, 'source_sha256': {str(p.relative_to(rom)): digest(p) for p in inputs},
        'build_inputs': {str(p.relative_to(rom)): digest(p) for p in (sdk, lambda_stubs, aapt, r8, signer, java, javac)},
        'upstream_audit': {'path': str(audit), 'sha256': digest(audit),
                           'project_count': report['project_count'], 'public_repositories': len(report['repositories'])},
        'toolchain_audit': {'path': str(toolaudit), 'sha256': digest(toolaudit)},
        'commands': commands, 'log': str(log),
    }
    output = work/'build-review.json'
    output.write_text(json.dumps(receipt, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({k: receipt[k] for k in ('core_tests', 'apk', 'apk_bytes', 'apk_sha256')}, indent=2))


if __name__ == '__main__':
    main()
