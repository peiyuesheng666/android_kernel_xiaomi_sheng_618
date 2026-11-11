#!/usr/bin/env python3
"""Compare shipping charger callbacks to r76 using instruction-level property anchors."""
from pathlib import Path
import json
import re
import subprocess

workspace = Path(__file__).resolve().parents[1]
stock = workspace/'logs/charging-computer-baseline-20261111-173127/stock-qti-battery-charger.ko'
source_path = Path('/root/sheng-618-pen-release-build/k618/soc/drivers/power/supply/qti_battery_charger.c')
module = Path('/root/sheng-618-pen-release-build/k618/soc/qti_battery_charger.ko')
source = source_path.read_text()
nm = lambda p: subprocess.check_output(['llvm-nm',str(p)],text=True)
attrs = lambda s: set(re.findall(r'\bclass_attr_(\w+)\s*$',s,re.M))
stock_nm, current_nm = nm(stock), nm(module)
stock_attrs, current_attrs = attrs(stock_nm), attrs(current_nm)
disasm_path = workspace/'logs/charging-computer-baseline-20261111-173127/stock-charger-full-disassembly.txt'
disasm = disasm_path.read_text()
bodies = {}
for part in re.split(r'(?=^[0-9a-f]+ <)',disasm,flags=re.M):
    match = re.match(r'([0-9a-f]+) <([\w.]+)>:',part)
    if match:
        bodies[match[2].split('.')[0]] = dict(address='0x'+match[1],instructions=part)
ids = {name:int(value) for name,value in re.findall(r'\b(XM_PROP_\w+)\s*=\s*(\d+)',source)}
rows = []
for name in sorted(stock_attrs):
    row = dict(node=name,missing=name not in current_attrs,callbacks={})
    for operation in ('show','store'):
        key = name+'_'+operation
        if key not in bodies:
            continue
        b = bodies[key]
        imm = [int(x,0) for x in re.findall(r'\bmov\s+x\d+, #(0x[0-9a-f]+|\d+)',b['instructions'])]
        anchors = sorted(set(v>>32 for v in imm if v >= 1<<32 and not v & ((1<<32)-1) and 0 < v>>32 < 1024))
        parser = re.findall(r'R_AARCH64_CALL26\s+(kstrto\w+)',b['instructions'])
        current = re.search(r'static ssize_t '+re.escape(key)+r'\([^{}]*\)\s*\{(.*?)^\}',source,re.M|re.S)
        props = sorted(set(re.findall(r'\bXM_PROP_\w+\b',current[1]))) if current else []
        item = dict(address=b['address'],composite_property_anchors=anchors,
                    parsers=parser,current_properties={p:ids.get(p) for p in props})
        if operation == 'show' and len(anchors)==1:
            prop = anchors[0]
            item['cache_offset_anchor'] = bool(re.search(r'ldr\s+w3, \[x\d+, #'+str(prop*4)+r'\]',b['instructions']))
        row['callbacks'][operation] = item
    rows.append(row)
report = dict(stock_module=str(stock),source=str(source_path),module=str(module),
    stock_attribute_count=len(stock_attrs),current_attribute_count=len(current_attrs),
    missing_attribute_count=len(stock_attrs-current_attrs),current_max_property=ids['XM_PROP_MAX'],
    automatic_anchors_are_candidates_until_reviewed=True,rows=rows)
out = workspace/'reports/kernel618-charging-interfaces-r85-audit.json'
out.write_text(json.dumps(report,indent=2)+'\n')
for row in rows:
    anchors = row['callbacks'].get('show',{}).get('composite_property_anchors',[])
    old = row['callbacks'].get('show',{}).get('current_properties',{})
    if row['missing'] or (len(anchors)==1 and old and anchors[0] not in old.values()):
        print(json.dumps(row))
print(json.dumps(dict(report=str(out),missing=report['missing_attribute_count'])))
