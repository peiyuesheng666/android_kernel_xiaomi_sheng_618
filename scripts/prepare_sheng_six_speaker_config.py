#!/usr/bin/env python3
"""Apply the original board's mixer overlays for HALs without Xiaomi's merger."""
from pathlib import Path
import copy
import json
import shutil
import xml.etree.ElementTree as ET

workspace = Path(__file__).resolve().parents[1]
stock = Path('/root/sheng-lineage/firmware-dump/partitions/odm/etc/audio/sku_kalama')
base = ET.parse(stock / 'mixer_paths_kalama_mtp.xml').getroot()
for filename in ('mixer_paths_overlay_static.xml', 'mixer_paths_overlay_dynamic.xml'):
    overlay = ET.parse(stock / filename).getroot()
    for element in overlay:
        assert element.tag in ('ctl', 'path')
        existing = [item for item in base if item.tag == element.tag and
                    item.get('name') == element.get('name')]
        assert len(existing) <= 1, (filename, element.tag, element.get('name'))
        if existing:
            index = list(base).index(existing[0])
            base.remove(existing[0])
        else:
            assert element.tag == 'ctl', (filename, element.get('name'))
            index = next(i for i, item in enumerate(base) if item.tag == 'path')
        base.insert(index, copy.deepcopy(element))

speaker = base.find("path[@name='speaker']")
amps = ('TLH', 'TLL', 'TRL', 'BLH', 'BLL', 'BRL')
for amp in amps:
    assert speaker.find("ctl[@name='" + amp + " AMP Enable Switch']").get('value') == '1'
    assert speaker.find("ctl[@name='" + amp + " PCM Source']").get('value') == 'DSP'

ET.indent(base)
destination = workspace / 'artifacts/system-services-sheng-r2/mixer_paths_sheng.xml'
ET.ElementTree(base).write(destination, encoding='utf-8', xml_declaration=True)
source_config = workspace / 'device/xiaomi/sheng/configs/audio'
shutil.copyfile(destination, source_config / 'mixer_paths_kalama_mtp.xml')
shutil.copyfile(stock / 'resourcemanager_kalama_mtp.xml',
                source_config / 'resourcemanager_kalama_mtp.xml')
resources = ET.parse(stock / 'resourcemanager_kalama_mtp.xml')
speakers = [item for item in resources.iter('out-device')
            if item.findtext('id') == 'PAL_DEVICE_OUT_SPEAKER']
assert len(speakers) == 1
assert speakers[0].findtext('back_end_name') == 'TDM-LPAIF-RX-SECONDARY'
report = {'speaker_backend': 'TDM-LPAIF-RX-SECONDARY', 'physical_amplifier_routes': amps,
          'hardware_channels': speakers[0].findtext('channels'),
          'gain_and_protection_values': 'unchanged from stock overlays',
          'hardware_output_verified': False}
(destination.parent / 'six-speaker-config.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
