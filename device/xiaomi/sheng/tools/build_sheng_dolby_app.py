#!/usr/bin/env python3
"""Build resources and Java for ShengDolby alone using existing ROM tool outputs."""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import tempfile
import zipfile

device = Path(__file__).resolve().parents[1]
workspace = device.parents[2]
rom = Path('/root/sheng-lineage/lineage-24.0')
source = workspace / 'device/xiaomi/sheng/dolby/ShengDolby'
target = rom / 'device/xiaomi/sheng/dolby/ShengDolby'
artifact = workspace / 'artifacts/audio-diagnostics-sheng'
previous = rom / 'out/target/product/sheng/system_ext/priv-app/ShengDolby/ShengDolby.apk'
rollback = artifact / 'ShengDolby-offload-r1.apk'
if not rollback.exists():
    shutil.copyfile(previous, rollback)
build = Path(tempfile.mkdtemp(prefix='dolby-app-settings-', dir='/root/sheng-lineage'))
classes, dex, generated = build/'classes', build/'dex', build/'generated'
for directory in (classes, dex, generated):
    directory.mkdir()
java = rom / 'prebuilts/jdk/jdk21/linux-x86/bin'
framework = rom / 'out/soong/.intermediates/frameworks/base/framework-minus-apex/android_common/combined/framework.jar'
sdk = rom / 'prebuilts/sdk/current/public/android.jar'
aapt = rom / 'out/host/linux-x86/bin/aapt2'
os.environ.update(LANG='C.UTF-8', LC_ALL='C.UTF-8')
def run(args):
    subprocess.run(list(map(str, args)), check=True)
compiled = build/'resources.zip'
run([aapt, 'compile', '--dir', source/'res', '-o', compiled])
resources = build/'resources.apk'
run([aapt, 'link', '-I', sdk, '--manifest', source/'AndroidManifest.xml',
     '--min-sdk-version', '35', '--target-sdk-version', '37',
     '--java', generated, '-o', resources, compiled])
run([java/'javac', '-source', '8', '-target', '8', '-cp', str(framework)+':'+str(sdk),
     '-d', classes, *source.rglob('*.java'), *generated.rglob('*.java')])
run([java/'java', '-cp', rom/'out/host/linux-x86/framework/d8.jar',
     'com.android.tools.r8.D8', '--lib', sdk, '--min-api', '35', '--output', dex,
     *classes.rglob('*.class')])
unsigned = build/'ShengDolby-unsigned.apk'
with zipfile.ZipFile(resources) as original, zipfile.ZipFile(unsigned, 'w') as output:
    for item in original.infolist():
        output.writestr(item, original.read(item.filename))
    output.write(dex/'classes.dex', 'classes.dex', compress_type=zipfile.ZIP_STORED)
candidate = artifact/'ShengDolby-settings-r2.apk'
run([java/'java', '-Djava.library.path='+str(rom/'out/host/linux-x86/lib64'),
     '-jar', rom/'out/host/linux-x86/framework/signapk.jar',
     rom/'build/target/product/security/platform.x509.pem',
     rom/'build/target/product/security/platform.pk8', unsigned, candidate])
print('Built '+str(candidate)+' SHA256='+hashlib.sha256(candidate.read_bytes()).hexdigest())
print('Build directory: '+str(build))
