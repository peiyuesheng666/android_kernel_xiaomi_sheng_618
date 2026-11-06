#!/usr/bin/env python3
"""Rebuild only sheng's small framework overlay using its existing link rule."""
from pathlib import Path
import re
import shlex
import shutil
import subprocess

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
host = rom / 'out/host/linux-x86/bin'
build = Path('/root/sheng-lineage/tablet-mode-overlay-r2')
build.mkdir(exist_ok=True)
compiled = build / 'resources'
compiled.mkdir(exist_ok=True)
section = (rom / 'out/soong/build.lineage_sheng.0.ninja').read_text().split(
    '# Module:  FrameworkResOverlaySheng\n', 1)[1].split('# Module:', 1)[0]
flags = re.search(r'^    flags = (--enable-compact-entries[^\n]+)$', section, re.M).group(1)
flags = re.sub(r'\$\$\(: [0-9a-f]+\)', '', flags)

def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)

run([host / 'aapt2', 'compile', '--pseudo-localize', '--dir',
     rom / 'device/xiaomi/sheng/overlay/FrameworkResOverlaySheng/res', '-o', compiled])
unsigned = build / 'unsigned.apk'
run([host / 'aapt2', 'link', *shlex.split(flags), '-o', unsigned,
     *sorted(compiled.glob('*.flat'))], cwd=rom)
destination = workspace / 'artifacts/system-services-sheng-r2/FrameworkResOverlaySheng.apk'
signed = build / 'FrameworkResOverlaySheng.apk'
run([rom / 'prebuilts/jdk/jdk21/linux-x86/bin/java',
     '-Djava.library.path=' + str(host.parent / 'lib64'), '-jar',
     host.parent / 'framework/signapk.jar', '--disable-v1',
     rom / 'build/make/target/product/security/testkey.x509.pem',
     rom / 'build/make/target/product/security/testkey.pk8', unsigned, signed], cwd=rom)
shutil.copyfile(signed, destination)
resources = run([host / 'aapt2', 'dump', 'resources', destination],
                capture_output=True, text=True).stdout
for name in ('config_canInternalDisplayHostDesktops', 'config_isDesktopModeSupported',
             'config_isDesktopModeDevOptionSupported', 'config_enterDesktopByDefaultOnFreeformDisplay'):
    assert re.search(r'\b' + name + r'\b[^\n]*\n\s*\(\) false\b', resources), name
(destination.parent / 'overlay-resources.txt').write_text(resources)
print(destination)
