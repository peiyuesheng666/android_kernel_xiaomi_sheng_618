#!/usr/bin/env python3
"""Summarize pen contact transitions and captured raw flag gaps without modifying data."""
import collections
import json
from pathlib import Path
import re
import struct
import sys

folder=Path(sys.argv[1])
capture=json.loads((folder/'capture.json').read_text())
assert capture['event']=='event6','The first r85 capture selected event0 and is not a pen-event baseline'
raw=(folder/'frames.bin').read_bytes()
magic,stride=struct.unpack_from('<II',raw)
assert magic==0x31505453 and stride==8192
frames=[];types=collections.Counter();fragments=collections.Counter()
for pos in range(8,len(raw)-stride-11,stride+12):
    timestamp,sequence=struct.unpack_from('<qq',raw,pos+12)
    p=raw[pos+36:pos+36+5160]
    types[(p[0],struct.unpack_from('<I',p,8)[0])]+=1
    if p[56]==29:
        flag=(p[75],struct.unpack_from('<H',p,68)[0],p[80])
        fragments[flag]+=1
    frames.append((timestamp/1e9,p))
starts=0;last_down=False;raw_gaps=[];last_down_time=None;gap=False
for t,p in frames:
    down=p[56]==29 and struct.unpack_from('<H',p,68)[0]==16 and p[80]==0
    starts+=down and not last_down
    if down:
        if gap and last_down_time is not None:raw_gaps.append(round((t-last_down_time)*1000,3))
        last_down_time=t;gap=False
    elif last_down_time is not None:gap=True
    last_down=down
states=collections.defaultdict(int);events=[]
for line in (folder/'events.txt').read_text().splitlines():
    m=re.match(r'\[\s*([0-9.]+)\]\s+(EV_\w+)\s+(\w+)\s+(\w+)',line)
    if not m:continue
    t=float(m[1]);typ,key,value=m.groups()[1:]
    if value in ('DOWN','UP'):value=1 if value=='DOWN' else 0
    else:
        value=int(value,16)
        if value>=1<<31:value-=1<<32
    if typ!='EV_SYN':states[key]=value
    elif key=='SYN_REPORT':events.append((t,dict(states)))
touch_starts=0;last=False;last_t=None;had_zero=False;gaps=[]
for t,s in events:
    touch=bool(s.get('BTN_TOUCH',0));touch_starts+=touch and not last
    if not s.get('BTN_DIGI',0):last_t=None;had_zero=False
    elif touch:
        if had_zero and last_t is not None:gaps.append(round((t-last_t)*1000,3))
        last_t=t;had_zero=False
    else:had_zero=True
    last=touch
report=dict(capture=capture,raw_frames=len(frames),protocols=[dict(protocol=k[0],words=k[1],count=v) for k,v in types.items()],
    raw_fragment_counts=[dict(flag=k[0],contact=k[1],distance=k[2],count=v) for k,v in fragments.items()],
    raw_contact_starts=starts,evdev_syn_reports=len(events),evdev_contact_starts=touch_starts,
    raw_short_gap_histogram_ms=dict(sorted(collections.Counter(round(v) for v in raw_gaps if v<100).items())),
    evdev_short_gap_histogram_ms=dict(sorted(collections.Counter(round(v) for v in gaps if v<100).items())),
    gap_classification_limitation='Intentional pen lifts also appear as gaps; counts alone do not prove unintended disconnects')
(folder/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
