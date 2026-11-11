#!/usr/bin/env python3
"""Restore shipping scalar charging interfaces with verified IDs and parsers."""
from pathlib import Path
import difflib
import hashlib
import json
import re
import struct

workspace=Path(__file__).resolve().parents[1]
project=Path('/root/sheng-618-repair-r85-project')
build=Path('/root/sheng-618-repair-r85-build')
receipt_path=project/'provenance/repair-r85.json'
receipt=json.loads(receipt_path.read_text())
source_path=build/'k618/soc/drivers/power/supply/qti_battery_charger.c'
source=source_path.read_text()
assert hashlib.sha256(source.encode()).hexdigest()==receipt['files']['k618/soc/drivers/power/supply/qti_battery_charger.c']['after']
audit=json.loads((workspace/'reports/kernel618-charging-interfaces-r85-audit.json').read_text())
stock=workspace/'logs/charging-computer-baseline-20261111-173127/stock-qti-battery-charger.ko'
blob=stock.read_bytes()
assert blob[:6]==b'\x7fELF\x02\x01'
shoff=struct.unpack_from('<Q',blob,40)[0]
shsize,shcount,strindex=struct.unpack_from('<HHH',blob,58)
sections=[struct.unpack_from('<IIQQQQIIQQ',blob,shoff+i*shsize) for i in range(shcount)]
strings=blob[sections[strindex][4]:sections[strindex][4]+sections[strindex][5]]
section=next(s for s in sections if strings[s[0]:].split(b'\0',1)[0]==b'.rodata')
rodata=blob[section[4]:section[4]+section[5]]
disasm=(workspace/'logs/charging-computer-baseline-20261111-173127/stock-charger-full-disassembly.txt').read_text()
bodies={}
for part in re.split(r'(?=^[0-9a-f]+ <)',disasm,flags=re.M):
    m=re.match(r'[0-9a-f]+ <([\w.]+)>:',part)
    if m: bodies[m[1].split('.')[0]]=part
rows=[];deferred=[]
for row in audit['rows']:
    if not row['missing'] or row['node']=='charging_suspend_battery':continue
    show=row['callbacks'].get('show',{})
    ids=show.get('composite_property_anchors',[])
    if len(ids)!=1 or not show.get('cache_offset_anchor'):
        deferred.append(row['node']);continue
    prop=ids[0]
    body=bodies[row['node']+'_show']
    formats=[]
    for offset in re.findall(r'R_AARCH64_ADR_PREL_PG_HI21\s+\.rodata\+0x([a-f0-9]+)',body):
        data=rodata[int(offset,16):].split(b'\0',1)[0]
        if data in (b'%u\n',b'%d\n',b'%u',b'%d'):formats.append(data.decode())
    assert len(set(formats))==1,(row['node'],formats)
    parser=None
    if 'store' in row['callbacks']:
        store=row['callbacks']['store']
        assert store['composite_property_anchors']==[prop],row['node']
        assert len(store['parsers'])==1,row['node']
        parser=store['parsers'][0]
        assert parser in ('kstrtobool','kstrtoint','kstrtouint'),(row['node'],parser)
    rows.append(dict(node=row['node'],id=prop,format=formats[0],parser=parser,
                     show_address=show['address'],store_address=row['callbacks'].get('store',{}).get('address')))
header='''/* SPDX-License-Identifier: GPL-2.0-only */
/* Shipping sheng scalar charger ABI. No default property writes. */
static int sheng_charging_live(struct battery_chg_dev *bcdev)
{
    return atomic_read(&bcdev->state) == PMIC_GLINK_STATE_UP &&
           !(bcdev->debug_battery_detected && bcdev->block_tx);
}

static ssize_t sheng_charging_show(struct battery_chg_dev *bcdev,
        u32 id, const char *format, char *buf)
{
    struct psy_state *pst = &bcdev->psy_list[PSY_TYPE_XM];
    int rc;
    if (!sheng_charging_live(bcdev))
        return -ENOTCONN;
    rc = read_property_id(bcdev, pst, id);
    if (rc < 0)
        return rc;
    if (!sheng_charging_live(bcdev))
        return -ENOTCONN;
    return scnprintf(buf, PAGE_SIZE, format, READ_ONCE(pst->prop[id]));
}

static ssize_t sheng_charging_store(struct battery_chg_dev *bcdev,
        u32 id, u32 value, size_t count)
{
    int rc;
    if (!sheng_charging_live(bcdev))
        return -ENOTCONN;
    rc = write_property_id(bcdev, &bcdev->psy_list[PSY_TYPE_XM], id, value);
    if (rc < 0)
        return rc;
    if (!sheng_charging_live(bcdev))
        return -ENOTCONN;
    return count;
}

'''
for row in rows:
    name,prop=row['node'],row['id']
    format_literal=json.dumps(row['format'])
    header+=f'''static ssize_t {name}_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, {prop}, {format_literal}, buf);
}}
'''
    if row['parser']:
        parser=row['parser'];typename='bool' if parser=='kstrtobool' else ('int' if parser=='kstrtoint' else 'unsigned int')
        parse=f'{parser}(buf, &value)' if parser=='kstrtobool' else f'{parser}(buf, 0, &value)'
        header+=f'''static ssize_t {name}_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    {typename} value;
    if ({parse})
        return -EINVAL;
    return sheng_charging_store(bcdev, {prop}, value, count);
}}
static CLASS_ATTR_RW({name});

'''
    else:header+=f'static CLASS_ATTR_RO({name});\n\n'
header_path=build/'k618/soc/drivers/power/supply/sheng_charging_interfaces.h'
assert not header_path.exists()
header_path.write_text(header)
anchor='static struct attribute *battery_class_attrs[] = {'
assert source.count(anchor)==1
source=source.replace(anchor,'#include "sheng_charging_interfaces.h"\n\n'+anchor+
    ''.join('\n\t&class_attr_'+r['node']+'.attr,' for r in rows))
for name,old,new in (('FG_VENDOR_ID',217,216),('DAM_OVPGATE',219,218),('IS_EU_MODEL',221,230),
                     ('PPS_PTF',222,231),('LAST_NODE',229,232),('MAX',230,233)):
    pattern=r'\bXM_PROP_'+name+' = '+str(old)+r'\b'
    assert len(re.findall(pattern,source))==1,name
    source=re.sub(pattern,'XM_PROP_'+name+' = '+str(new),source)
source_path.write_text(source)
relative='k618/soc/drivers/power/supply/qti_battery_charger.c'
receipt['files'][relative]['after']=hashlib.sha256(source.encode()).hexdigest()
base=(Path('/root/sheng-618-pen-release-build')/relative).read_text()
patch=''.join(difflib.unified_diff(base.splitlines(True),source.splitlines(True),fromfile='a/'+relative,tofile='b/'+relative))
header_relative=str(header_path.relative_to(build))
patch+=''.join(difflib.unified_diff([],header.splitlines(True),fromfile='/dev/null',tofile='b/'+header_relative))
(project/receipt['patch']).write_text(patch)
receipt['files'][header_relative]=dict(before=None,after=hashlib.sha256(header.encode()).hexdigest())
receipt['patch_sha256']=hashlib.sha256(patch.encode()).hexdigest()
receipt['restored_scalar_nodes']=rows
receipt['deferred_non_scalar_nodes']=deferred
receipt['stock_property_array_size']=233
receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
(workspace/'reports/kernel618-repair-r85-stage.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(dict(restored=len(rows),deferred=deferred,property_array_size=233,source_sha256=receipt['files'][relative]['after'])),flush=True)
