#!/usr/bin/env python3
"""Capture unfiltered THP and pen events, restoring the original filter on exit."""
from pathlib import Path
import argparse
import json
import re
import subprocess
import time

workspace=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--keep-filter',action='store_true')
parser.add_argument('--seconds',type=int,default=90)
args=parser.parse_args()
assert 20 <= args.seconds <= 120
adb=[str(workspace/'tools/platform-tools/adb.exe'),'-s','192.168.1.14:5555']
def call(command,root=False):
    if root:
        command="su -c '"+command.replace("'","'\"'\"'")+"'"
    p=subprocess.run(adb+['shell',command],capture_output=True,timeout=25)
    assert p.returncode==0,(command,p.stderr)
    return p.stdout.decode(errors='replace').strip()
assert call('getprop ro.serialno')=='603ac302'
folder=workspace/'logs'/('r85-pen-'+time.strftime('%Y%m%d-%H%M%S'))
folder.mkdir()
inputs=call('cat /proc/bus/input/devices')
blocks=re.split(r'\r?\n\r?\n',inputs)
block=next(b for b in blocks if 'Name="NVTCapacitivePenP81c"' in b)
event=re.search(r'Handlers=.*\b(event\d+)\b',block)[1]
(folder/'input-before.txt').write_text(inputs)
(folder/'dmesg-before.txt').write_text(call('dmesg',True))
param='/sys/module/nt36532_touch/parameters/sheng_pen_contact_hold_ms'
old=call('cat '+param,True)
assert old in ('0','32')
binary=workspace/'logs/sheng-touch-frame-probe-r85'
win_binary=subprocess.check_output(['wslpath','-w',str(binary)],text=True).strip()
subprocess.run(adb+['push',win_binary,'/data/local/tmp/sheng-touch-frame-probe-r85'],check=True,capture_output=True)
call('chmod 755 /data/local/tmp/sheng-touch-frame-probe-r85',True)
remote='/data/local/tmp/'+folder.name+'-frames.bin'
processes=[]
files=[]
try:
    if not args.keep_filter:
        call('echo 0 > '+param,True)
    for command,filename in ((f'/data/local/tmp/sheng-touch-frame-probe-r85 {remote} {args.seconds}','raw-capture.txt'),
                              (f'timeout {args.seconds+5} getevent -lt /dev/input/'+event,'events.txt')):
        stream=(folder/filename).open('wb');files.append(stream)
        root_command="su -c '"+command+"'"
        processes.append(subprocess.Popen(adb+['shell',root_command],stdout=stream,stderr=subprocess.STDOUT))
    print(json.dumps(dict(stage='capture_ready',folder=str(folder),duration_seconds=args.seconds,event=event,
                         filter_during=old if args.keep_filter else '0')),flush=True)
    for i in range(args.seconds//5):
        time.sleep(5)
        (folder/f'state-{i:02d}.txt').write_text(call('cat /proc/uptime /proc/xm_htc_stylus_enable /sys/class/touch/touch_dev/pen_connect_strategy',True))
        if processes[0].poll() is not None:
            break
    for p in processes:
        if p.poll() is None:
            p.terminate()
        p.wait(timeout=10)
finally:
    for p in processes:
        if p.poll() is None:
            p.terminate()
    for stream in files:
        stream.close()
    call('echo '+old+' > '+param,True)
(folder/'dmesg-after.txt').write_text(call('dmesg',True))
win_output=subprocess.check_output(['wslpath','-w',str(folder/'frames.bin')],text=True).strip()
subprocess.run(adb+['pull',remote,win_output],check=True,capture_output=True)
(folder/'capture.json').write_text(json.dumps(dict(serial='603ac302',event=event,filter_before=old,
    filter_during=old if args.keep_filter else '0',filter_after=call('cat '+param,True),boot_id=call('cat /proc/sys/kernel/random/boot_id'),
    purpose='single taps and continuous strokes',raw_bytes=(folder/'frames.bin').stat().st_size),indent=2)+'\n')
print(json.dumps(dict(stage='complete',folder=str(folder))),flush=True)
