#!/usr/bin/env python3
"""Build only ShengDolby, preserving the previous app as a rollback artifact."""
from pathlib import Path
import os
import shutil
import subprocess
import zipfile

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
source = workspace / 'device/xiaomi/sheng/dolby/ShengDolby'
target = rom / 'device/xiaomi/sheng/dolby/ShengDolby'
artifact = workspace / 'artifacts/audio-diagnostics-sheng'
apk = rom / 'out/target/product/sheng/system_ext/priv-app/ShengDolby/ShengDolby.apk'
rollback = artifact / 'ShengDolby-offload-r1.apk'
if not rollback.exists():
    shutil.copyfile(apk, rollback)
# Reuse the installed app's manifest/resources and already-built platform
# stubs. No build graph traversal or framework rebuild is necessary.
build = Path('/root/sheng-lineage/dolby-app-lifecycle')
classes = build / 'classes'
dex = build / 'dex'
classes.mkdir(parents=True, exist_ok=True)
dex.mkdir(exist_ok=True)
java = rom / 'prebuilts/jdk/jdk21/linux-x86/bin'
framework = rom / 'out/soong/.intermediates/frameworks/base/framework-minus-apex/android_common/combined/framework.jar'
resources = rom / 'out/soong/.intermediates/device/xiaomi/sheng/dolby/ShengDolby/ShengDolby/android_common/busybox/R.jar'
sdk = rom / 'prebuilts/sdk/current/public/android.jar'
os.environ.update(LANG='C.UTF-8', LC_ALL='C.UTF-8')
subprocess.run([str(java/'javac'), '-source', '8', '-target', '8', '-cp',
    ':'.join(map(str, (framework, resources, sdk))), '-d', str(classes),
    *map(str, source.rglob('*.java'))], check=True)
subprocess.run([str(java/'java'), '-cp', str(rom/'out/host/linux-x86/framework/d8.jar'),
    'com.android.tools.r8.D8', '--lib', str(sdk), '--min-api', '35', '--output', str(dex),
    *map(str, classes.rglob('*.class')), str(resources)], check=True)
unsigned = build / 'ShengDolby-unsigned.apk'
with zipfile.ZipFile(rollback) as original, zipfile.ZipFile(unsigned, 'w') as output:
    for item in original.infolist():
        if not item.filename.startswith('META-INF/') and not item.filename.endswith('.dex'):
            output.writestr(item, original.read(item.filename))
    output.write(dex/'classes.dex', 'classes.dex', compress_type=zipfile.ZIP_STORED)
candidate = artifact / 'ShengDolby-lifecycle.apk'
subprocess.run([str(java/'java'), '-Djava.library.path='+str(rom/'out/host/linux-x86/lib64'),
    '-jar', str(rom/'out/host/linux-x86/framework/signapk.jar'),
    str(rom/'build/target/product/security/platform.x509.pem'),
    str(rom/'build/target/product/security/platform.pk8'), str(unsigned), str(candidate)], check=True)
for path in source.rglob('*.java'):
    shutil.copyfile(path, target/path.relative_to(source))
print('Built and platform-signed ShengDolby lifecycle candidate without rebuilding dependencies.')
