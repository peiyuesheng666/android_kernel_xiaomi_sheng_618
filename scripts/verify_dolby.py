#!/usr/bin/env python3
"""Check native Dolby integration and compile the independent UI resources.

This does not assert runtime DSP behavior or a completed Android ROM build.
"""
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

os.environ['LC_ALL'] = 'C.UTF-8'
os.environ['LANG'] = 'C.UTF-8'

WORK = Path(__file__).resolve().parents[1]
DEVICE = WORK / 'device/xiaomi/sheng'
ROOT = Path('/root/sheng-lineage')
ROM = ROOT / 'lineage-24.0'
app = DEVICE / 'dolby/ShengDolby'
output = ROOT / 'out/verify-dolby'
output.mkdir(parents=True, exist_ok=True)
sdk = Path('/mnt/c/Users/Dev裴月笙/AppData/Local/Android/Sdk/platforms/android-37.0/android.jar')
aapt = ROOT / 'tools/aapt2/aapt2'
res = output / 'resources.zip'
subprocess.run([str(aapt), 'compile', '--dir', str(app / 'res'), '-o', str(res)], check=True)
subprocess.run([str(aapt), 'link', '-I', str(sdk), '--manifest', str(app / 'AndroidManifest.xml'),
                '--java', str(output / 'generated'), '--min-sdk-version', '33',
                '--target-sdk-version', '37', '-o', str(output / 'resources.apk'), str(res)], check=True)
# AudioEffect's generic constructor is a non-SDK platform API. The real module
# declares platform_apis=true; public SDK stubs intentionally cannot compile it.
# Keep that validation in the full Android build rather than substitute a stub.
assert 'platform_apis: true' in (app / 'Android.bp').read_text()

report = json.loads((WORK / 'reports/dolby-integration.json').read_text())
vendor = ROM / 'vendor/xiaomi/sheng/proprietary'
for source in report['stock_inputs']:
    assert (vendor / source).is_file(), f'Missing extracted Dolby file: {source}'
xml = DEVICE / 'configs/audio/sku_kalama/audio_effects.xml'
ns = {'fx': 'http://schemas.android.com/audio/audio_effects_conf/v2_0'}
tree = ET.parse(xml)
effect = tree.find("fx:effects/fx:effect[@name='dap']", ns)
assert effect is not None and effect.get('uuid') == report['dap_uuid']
assert tree.find("fx:libraries/fx:library[@name='dap']", ns).get('path') == 'libhwdap.so'
manifest = ET.parse(vendor / 'vendor/etc/vintf/manifest/vendor.dolby.hardware.dms.xml')
assert manifest.find('.//hal/version').text == '2.0'
codec = ET.parse(vendor / 'vendor/etc/media_codecs_dolby_audio.xml')
assert codec.find(".//Type[@name='audio/eac3-joc']") is not None
active_media = (vendor / 'vendor/etc/media_codecs_kalama.xml').read_text()
assert 'media_codecs_dolby_audio.xml' in active_media
assert 'IComponentStore/dolby' in (vendor / 'vendor/etc/vintf/manifest/c2_manifest_vendor.xml').read_text()
results = {'resource_api37_compilation_passed': True,
           'java_platform_api_compilation': 'pending full Android build',
           'native_dap_uuid_and_library_verified': True, 'hidl_dms2_verified': True,
           'eac3_joc_decoder_manifest_preserved': True,
           'stock_input_count_verified': len(report['stock_inputs']),
           'full_rom_compiled': False, 'device_audio_runtime_validated': False}
(WORK / 'reports/dolby-preflight.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
