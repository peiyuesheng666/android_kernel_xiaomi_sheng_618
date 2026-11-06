#!/usr/bin/env python3
from pathlib import Path
import os
import subprocess
import tempfile
device = Path(__file__).resolve().parents[1]
workspace = device.parents[2]
rom = Path('/root/sheng-lineage/lineage-24.0')
output = Path(tempfile.mkdtemp(prefix='sheng-sensor-probe-', dir='/root/sheng-lineage'))
java = rom/'prebuilts/jdk/jdk21/linux-x86/bin'
sdk = rom/'prebuilts/sdk/current/public/android.jar'
framework = rom/'out/soong/.intermediates/frameworks/base/framework-minus-apex/android_common/combined/framework.jar'
env = dict(os.environ, LANG='C.UTF-8', LC_ALL='C.UTF-8')
subprocess.run([str(java/'javac'), '-cp', str(framework)+':'+str(sdk), '-d', str(output),
                str(device/'scripts'/os.environ.get('SHENG_PROBE_SOURCE', 'ShengSensorProbe.java'))], env=env, check=True)
subprocess.run([str(java/'java'), '-cp', str(rom/'out/host/linux-x86/framework/d8.jar'),
                'com.android.tools.r8.D8', '--lib', str(sdk), '--min-api', '35',
                '--output', str(output), *map(str, output.glob('*.class'))], env=env, check=True)
subprocess.run([str(java/'jar'), 'cf', str(workspace/'artifacts/audio-diagnostics-sheng'/
                os.environ.get('SHENG_PROBE_OUTPUT', 'sheng-sensor-probe.jar')),
                '-C', str(output), 'classes.dex'], env=env, check=True)
