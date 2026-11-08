#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the rootless wireless-debugging startup helper with public Android APIs."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import zipfile

p = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
src = p/'device/xiaomi/sheng/tools/WirelessAdbBoot'
out = Path('/root/sheng-618/tools/wireless-adb-boot')
delivery = p/'artifacts/sheng-wireless-adb-boot'
out.mkdir(parents=True, exist_ok=True)
delivery.mkdir(parents=True, exist_ok=True)
for d in ['classes', 'dex']:
    (out/d).mkdir(exist_ok=True)
java = rom/'prebuilts/jdk/jdk21/linux-x86/bin'
host = rom/'out/host/linux-x86'
sdk = rom/'prebuilts/sdk/36/public/android.jar'
env = dict(os.environ, JAVA_HOME=str(java.parent), PATH=str(java)+':'+os.environ['PATH'], LANG='C.UTF-8')
def run(args):
    return subprocess.run(list(map(str, args)), env=env, check=True)
run([java/'javac', '-source', '8', '-target', '8', '-encoding', 'UTF-8', '-cp', sdk,
     '-d', out/'classes', *sorted(src.rglob('*.java'))])
run([java/'java', '-cp', host/'framework/d8.jar', 'com.android.tools.r8.D8', '--lib', sdk,
     '--min-api', '31', '--output', out/'dex', *sorted((out/'classes').rglob('*.class'))])
unsigned = out/'unsigned.apk'
run([host/'bin/aapt2', 'link', '-I', sdk, '--manifest', src/'AndroidManifest.xml', '-o', unsigned])
with zipfile.ZipFile(unsigned, 'a') as z:
    z.write(out/'dex/classes.dex', 'classes.dex', compress_type=zipfile.ZIP_STORED)
aligned = out/'aligned.apk'
run([host/'bin/zipalign', '-f', '4', unsigned, aligned])
key = out/'development-signing.p12'
if not key.exists():
    run([java/'keytool', '-genkeypair', '-keystore', key, '-storetype', 'PKCS12', '-storepass', 'sheng-local-dev',
         '-alias', 'sheng-adb-boot', '-keyalg', 'RSA', '-keysize', '3072', '-validity', '3650',
         '-dname', 'CN=Sheng Wireless ADB Boot Development'])
apk = delivery/'ShengWirelessAdbBoot.apk'
run([host/'bin/apksigner', 'sign', '--ks', key, '--ks-key-alias', 'sheng-adb-boot',
     '--ks-pass', 'pass:sheng-local-dev', '--out', apk, aligned])
run([host/'bin/apksigner', 'verify', '--verbose', apk])
report = dict(apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(), bytes=apk.stat().st_size,
    package='org.peiyuesheng.sheng.adbboot', root_required=False, public_sdk=36,
    signing_key_private_local_only=True, settings_permission_requires_one_time_adb_grant=True,
    plain_tcp_listener_added=False, pairing_verification_changed=False,
    sources={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(src.rglob('*')) if f.is_file()})
(p/'reports/sheng-wireless-adb-boot-build.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
