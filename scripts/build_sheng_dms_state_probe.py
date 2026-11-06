#!/usr/bin/env python3
from pathlib import Path
import os
import subprocess
workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
output = Path('/root/sheng-lineage/dms-state-probe')
classes = output / 'classes'
dex = output / 'dex'
classes.mkdir(parents=True, exist_ok=True)
dex.mkdir(exist_ok=True)
java = rom / 'prebuilts/jdk/jdk21/linux-x86/bin'
sdk = rom / 'prebuilts/sdk/current/public/android.jar'
env = dict(os.environ, LANG='C.UTF-8', LC_ALL='C.UTF-8')
framework = rom / 'out/soong/.intermediates/frameworks/base/framework-minus-apex/android_common/combined/framework.jar'
subprocess.run([str(java/'javac'), '-source', '8', '-target', '8', '-cp', str(framework)+':'+str(sdk), '-d', str(classes),
                str(workspace/'scripts/ShengDmsStateProbe.java')], env=env, check=True)
subprocess.run([str(java/'java'), '-cp', str(rom/'out/host/linux-x86/framework/d8.jar'),
                'com.android.tools.r8.D8', '--lib', str(sdk), '--min-api', '35',
                '--output', str(dex), *map(str, classes.glob('ShengDmsStateProbe*.class'))],
               env=env, check=True)
destination = workspace/'artifacts/audio-diagnostics-sheng/sheng-dms-state-probe.jar'
subprocess.run([str(java/'jar'), 'cf', str(destination), '-C', str(dex), 'classes.dex'],
               env=env, check=True)
print('Built read-only DMS state probe.')
