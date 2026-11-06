#!/usr/bin/env python3
"""Derive hardware overlay values from the supplied sheng APK using Google aapt2."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

WORK = Path(__file__).resolve().parents[1]
ROOT = Path('/root/sheng-lineage')
AAPT = ROOT / 'tools/aapt2/aapt2'
APK = ROOT / 'firmware-dump/partitions/odm/overlay/FrameworksResTarget_Vendor.apk'
DEST = WORK / 'device/xiaomi/sheng/overlay/FrameworkResOverlaySheng/res'

dump = subprocess.check_output([str(AAPT), 'dump', 'resources', str(APK)], text=True)
values = ET.Element('resources')
arrays = {}
for name in ('config_autoBrightnessLevels', 'config_autoBrightnessLcdBacklightValues'):
    match = re.search(r'array/' + name + r'\n\s+\(\) \(array\) size=(\d+)\s+(\[[^\]]*\])', dump)
    assert match, f'Missing array {name}'
    data = json.loads(match[2])
    assert len(data) == int(match[1]) and all(isinstance(n, int) for n in data)
    arrays[name] = data
    array = ET.SubElement(values, 'integer-array', {'name': name})
    for value in data:
        ET.SubElement(array, 'item').text = str(value)
assert len(arrays['config_autoBrightnessLevels']) + 1 == len(arrays['config_autoBrightnessLcdBacklightValues'])
for name in ('config_screenBrightnessSettingMinimum', 'config_screenBrightnessSettingMaximum',
             'config_screenBrightnessSettingDefault', 'config_screenBrightnessDim', 'config_defaultRefreshRate'):
    match = re.search(r'integer/' + name + r'\n\s+\(\) (\d+)', dump)
    assert match, f'Missing integer {name}'
    ET.SubElement(values, 'integer', {'name': name}).text = match[1]
ET.indent(values)
(DEST / 'values/stock-display.xml').write_text(ET.tostring(values, encoding='unicode') + '\n')

dump_xml = subprocess.check_output([str(AAPT), 'dump', 'xmltree', str(APK), '--file', 'res/xml/power_profile.xml'], text=True)
root = None
stack = []
for line in dump_xml.splitlines():
    indent = len(line) - len(line.lstrip())
    text = line.strip()
    if text.startswith('E: '):
        tag = re.match(r'E: ([A-Za-z0-9_.-]+) \(line=\d+\)', text)
        assert tag, text
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            assert root is None
            root = ET.Element(tag[1])
            element = root
        else:
            element = ET.SubElement(stack[-1][1], tag[1])
        stack.append((indent, element))
    elif text.startswith('A: '):
        key, value = text[3:].split('=', 1)
        decoded, _ = json.JSONDecoder().raw_decode(value)
        assert isinstance(decoded, str)
        stack[-1][1].set(key, decoded)
    elif text.startswith('T: '):
        stack[-1][1].text = ast.literal_eval(text[3:])
    else:
        assert not text, text
assert root is not None and root.tag == 'device'
battery = root.find("item[@name='battery.capacity']")
assert battery is not None and float(battery.text) > 0
ET.indent(root)
(DEST / 'xml').mkdir(exist_ok=True)
(DEST / 'xml/power_profile.xml').write_text(ET.tostring(root, encoding='unicode') + '\n')
report = {'source_apk': str(APK), 'source_sha256': hashlib.sha256(APK.read_bytes()).hexdigest(),
          'aapt2_sha256': hashlib.sha256(AAPT.read_bytes()).hexdigest(),
          'aapt2_google_maven_version': '8.7.3-12006047', 'auto_brightness_arrays': arrays,
          'stock_battery_capacity_mah': float(battery.text),
          'note': 'Hardware data decoded from this stock package; no piano resources copied.'}
(WORK / 'reports/stock-overlay-derived.json').write_text(json.dumps(report, indent=2) + '\n')
print(f"Derived stock display curves and power profile ({battery.text} mAh)")
