#!/usr/bin/env python3
"""Idempotently apply the verified PAL patch and build that library only."""
from pathlib import Path
import os
import subprocess

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
repo = rom / 'hardware/qcom-caf/sm8550/audio/pal'
patch = workspace / 'patches/sheng-pcm-stereo-quad-coeff.patch'
assert patch.is_file()
applied = subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)],
                         cwd=repo, capture_output=True).returncode == 0
if not applied:
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=repo, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=repo, check=True)
print('Verified PCM patch already applied.' if applied else 'Applied verified PCM patch.')
environment = dict(os.environ)
environment['JAVA_HOME'] = str(rom / 'prebuilts/jdk/jdk21/linux-x86')
environment['PATH'] = environment['JAVA_HOME'] + '/bin:' + environment['PATH']
log = Path('/root/sheng-lineage/logs/sheng-pcm-speaker-library.log')
with log.open('w') as output:
    result = subprocess.run([str(rom / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                             '-f', 'out/combined-lineage_sheng.ninja', '-j8',
                             'out/target/product/sheng/vendor/lib64/libar-pal.so'],
                            cwd=rom, env=environment, stdout=output, stderr=subprocess.STDOUT)
print(log.read_text()[-1500:])
raise SystemExit(result.returncode)
