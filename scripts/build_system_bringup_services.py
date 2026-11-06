#!/usr/bin/env python3
"""Build only the modified services and policy with the ROM's Java runtime."""
import os
from pathlib import Path
import subprocess

rom = Path('/root/sheng-lineage/lineage-24.0')
environment = dict(os.environ)
environment['JAVA_HOME'] = str(rom / 'prebuilts/jdk/jdk21/linux-x86')
environment['PATH'] = environment['JAVA_HOME'] + '/bin:' + environment['PATH']
subprocess.run(['java', '-version'], env=environment, check=True)
targets = [
    'vendor/bin/hw/vendor.qti.hardware.display.allocator-service',
    'vendor/bin/hw/vendor.qti.hardware.display.composer-service',
    'vendor/bin/hw/android.hardware.sensors-service.xiaomi-multihal',
    'vendor/etc/selinux/vendor_sepolicy.cil',
    'vendor/etc/selinux/vendor_file_contexts',
    'obj/ETC/file_contexts.bin_intermediates/file_contexts.bin',
]
with Path('/root/sheng-lineage/logs/system-services-bringup-r2-final.log').open('w') as output:
    result = subprocess.run([
        str(rom / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-f', 'out/combined-lineage_sheng.ninja', '-j12',
        *['out/target/product/sheng/' + target for target in targets],
    ], cwd=rom, env=environment, stdout=output, stderr=subprocess.STDOUT)
raise SystemExit(result.returncode)
