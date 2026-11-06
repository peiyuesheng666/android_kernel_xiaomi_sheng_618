#!/usr/bin/env python3
"""Integrate the supplied sheng Dolby stack; all blob inputs are local stock copies."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

WORK = Path(__file__).resolve().parents[1]
DEVICE = WORK / 'device/xiaomi/sheng'
DUMP = Path('/root/sheng-lineage/firmware-dump/extract-source')
NS = 'http://schemas.android.com/audio/audio_effects_conf/v2_0'
q = lambda tag: '{' + NS + '}' + tag
ET.register_namespace('', NS)

seeds = {
    'vendor/bin/hw/vendor.dolby.hardware.dms@2.0-service',
    'vendor/etc/init/vendor.dolby.hardware.dms@2.0-service.rc',
    'vendor/etc/vintf/manifest/vendor.dolby.hardware.dms.xml',
    'vendor/etc/dolby/dax-default.xml', 'odm/etc/dolby/dax-default.xml',
    'vendor/bin/hw/vendor.dolby.media.c2@1.0-service',
    'vendor/bin/hw/dolbycodec2',
    'vendor/etc/init/vendor.dolby.media.c2@1.0-service.rc',
    'vendor/etc/init/dolbycodec2.rc', 'vendor/etc/media_codecs_dolby_audio.xml',
}
effects = ('libhwdap.so', 'libdlbvol.so', 'libswspatializer.so', 'libswgamedap.so', 'libswvqe.so')
for arch in ('lib', 'lib64'):
    seeds.update(f'vendor/{arch}/soundfx/{name}' for name in effects)
for name in ('libcodec2_soft_ddpdec.so', 'libcodec2_soft_ac4dec.so',
             'c2.dolby.hevc.dec.so', 'c2.dolby.hevc.sec.dec.so', 'c2.dolby.hevc.enc.so'):
    seeds.add('vendor/lib64/' + name)
platform = {'libc.so', 'libm.so', 'libdl.so', 'libc++.so', 'liblog.so', 'libutils.so',
            'libcutils.so', 'libbase.so', 'libhardware.so', 'libhidlbase.so', 'libhwbinder.so',
            'libhidltransport.so', 'libbinder.so', 'libbinder_ndk.so', 'libaudioutils.so',
            'libstagefright_foundation.so', 'libcodec2.so', 'libcodec2_vndk.so',
            'libcodec2_hidl@1.0.so', 'libcodec2_hidl@1.1.so', 'libcodec2_hidl@1.2.so',
            'libavservices_minijail.so', 'libfmq.so', 'libdmabufheap.so',
            'libcodec2_soft_common.so', 'libmemunreachable.so',
            'libstagefright_bufferpool@2.0.1.so', 'libqti_vndfwk_detect.so',
            'libsfplugin_ccodec_utils.so', 'libdrm.so',
            'vendor.qti.hardware.display.config-V2-ndk.so', 'libgui_vendor.so', 'libgui.so',
            'libprotobuf-cpp-full-3.9.1.so', 'libprotobuf-cpp-lite-3.9.1.so'}
queue = list(seeds)
selected = set()
while queue:
    relative = queue.pop()
    if relative in selected:
        continue
    file = DUMP / relative
    assert file.is_file(), f'Missing real stock Dolby input: {file}'
    selected.add(relative)
    with file.open('rb') as f:
        header = f.read(5)
    if header[:4] != b'\x7fELF':
        continue
    arch = 'lib64' if header[4] == 2 else 'lib'
    data = subprocess.check_output(['readelf', '-d', str(file)], text=True)
    for dependency in re.findall(r'\(NEEDED\).*\[([^\]]+)\]', data):
        if dependency in platform or dependency.startswith('android.'):
            continue
        candidate = f'vendor/{arch}/{dependency}'
        if (DUMP / candidate).is_file():
            queue.append(candidate)

inventory = DEVICE / 'proprietary-files.txt'
entries = {}
for line in inventory.read_text().splitlines():
    if line and not line.startswith('#'):
        destination = line.lstrip('-').split(';')[0].split('|')[0].split(':')[-1]
        entries[destination] = line
for file in selected:
    entries.setdefault(file, file)
inventory.write_text('# Standalone sheng stock blob inventory, including native Dolby stack.\n'
                     + '\n'.join(entries[name] for name in sorted(entries)) + '\n')

# Preserve stock Dolby definitions. Remove only the separate MIUI proprietary
# processing paths that would compete with the selected Dolby spatializer.
source = DUMP / 'vendor/etc/audio/sku_kalama/audio_effects.xml'
raw = source.read_text()
tree = ET.ElementTree(ET.fromstring(raw))
for parent_name, item_name in (('libraries', 'library'), ('effects', 'effect')):
    parent = tree.getroot().find(q(parent_name))
    for item in list(parent):
        if item.get('name') in ('shoebox', 'quasar', 'mispatializer'):
            parent.remove(item)
dap = tree.getroot().find(q('effects')).find(q('effect') + "[@name='dap']")
assert dap is not None and dap.get('uuid') == '9d4921da-8225-4f29-aefa-39537a04bcaa'
ET.indent(tree, space='    ')
preamble = raw[:raw.index('<audio_effects_conf')]
target = DEVICE / 'configs/audio/sku_kalama/audio_effects.xml'
target.write_text(preamble + ET.tostring(tree.getroot(), encoding='unicode') + '\n')

# Keep the fallback legacy file consistent with the XML factory configuration.
notices = '\n'.join(re.findall(r'<!--(.*?)-->', preamble, re.S))
lines = ['# ' + line for line in notices.splitlines()]
lines += ['# Generated from the stock sheng audio_effects.xml by prepare_dolby.py.', 'libraries {']
for library in tree.getroot().find(q('libraries')):
    lines.extend([f'  {library.get("name")} {{', f'    path /vendor/lib/soundfx/{library.get("path")}', '  }'])
lines.extend(['}', 'effects {'])
for effect in tree.getroot().find(q('effects')):
    lines.extend([f'  {effect.get("name")} {{', f'    library {effect.get("library")}', f'    uuid {effect.get("uuid")}'])
    for child in effect:
        lines.extend([f'    {child.tag.split("}")[-1]} {{', f'      library {child.get("library")}', f'      uuid {child.get("uuid")}', '    }'])
    lines.append('  }')
lines.append('}')
for xml_name, legacy_name in (('preprocess', 'pre_processing'), ('postprocess', 'post_processing')):
    section = tree.getroot().find(q(xml_name))
    if section is not None:
        lines.append(legacy_name + ' {')
        for stream in section:
            lines.append('  ' + stream.get('type') + ' {')
            for apply in stream:
                lines.append('    ' + apply.get('effect') + ' {}')
            lines.append('  }')
        lines.append('}')
target.with_suffix('.conf').write_text('\n'.join(lines) + '\n')
report = {'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'dolby_hidl': 'vendor.dolby.hardware.dms@2.0::IDms/default',
          'dap_uuid': dap.get('uuid'), 'stock_inputs': sorted(selected),
          'native_effect_names': [x.get('name') for x in tree.getroot().find(q('effects'))],
          'runtime_validated': False, 'android17_elf_compatibility_validated': False}
(WORK / 'reports/dolby-integration.json').write_text(json.dumps(report, indent=2) + '\n')
print(f'Prepared {len(selected)} Dolby inputs and consistent native effect configuration; runtime validation pending')
