#!/usr/bin/env python3
"""Resume read-only verification after the reboot closed wireless ADB."""
from pathlib import Path
import json
import subprocess
import time

workspace=Path(__file__).resolve().parents[1]
path=workspace/'reports/kernel618-repair-r87-wireless-flash.json'
state=json.loads(path.read_text())
assert any(e['event']=='full_partition_readback_verified' for e in state['events'])
assert state['serial']=='603ac302'
adb=str(workspace/'tools/platform-tools/adb.exe');address=state['address']
def call(command,root=False,timeout=30):
    if root:command="su -c '"+command.replace("'","'\"'\"'")+"'"
    p=subprocess.run([adb,'-s',address,'shell',command],capture_output=True,timeout=timeout)
    if p.returncode:raise RuntimeError((p.stdout+p.stderr).decode(errors='replace'))
    return p.stdout.decode(errors='replace').strip()
def event(name,**fields):
    state['events'].append(dict(event=name,**fields))
    path.write_text(json.dumps(state,indent=2)+'\n')
    print(json.dumps(state['events'][-1]),flush=True)
start=time.monotonic();notice=0
while time.monotonic()-start<240:
    try:
        subprocess.run([adb,'connect',address],capture_output=True,timeout=5)
        if call('getprop sys.boot_completed',timeout=6)=='1':
            assert call('getprop ro.serialno')=='603ac302'
            assert call('getprop ro.boot.slot_suffix')=='_a'
            boot_id=call('cat /proc/sys/kernel/random/boot_id')
            if boot_id!=state['boot_id_before']:
                event('wireless_android_boot_observed',boot_id=boot_id)
                assert call('sha256sum /dev/block/by-name/boot_a',True,90).split()[0]==state['image_sha256']
                assert call('sha256sum /dev/block/by-name/init_boot_a',True,90).split()[0]==state['init_boot_before_sha256']
                state.update(boot_id_after=boot_id,uname=call('uname -a'),cmdline=call('cat /proc/cmdline'),
                    pps_auto_verify=call('cat /sys/module/qti_battery_charger/parameters/sheng_pps_auto_verify',True))
                assert state['pps_auto_verify']=='Y'
                assert call('cat /sys/module/nt36532_touch/parameters/sheng_pen_contact_hold_ms')=='32'
                assert 'sheng_bootlog' not in state['cmdline']
                modules=call('cat /proc/modules')
                state['experimental_scheduler_modules']=[line.split()[0] for line in modules.splitlines()
                    if line.split()[0] in ('sched_walt','sched-walt','oplus_bsp_sched_assist','oplus_bsp_frame_boost','oplus_bsp_game_opt')]
                assert not state['experimental_scheduler_modules']
                state['reboot_disconnect_recovery']='Original reboot command lost its ADB connection; new Android boot and hashes verified without another flash'
                state['complete']=True
                event('android_boot_and_wireless_readback_verified');break
    except (RuntimeError,subprocess.TimeoutExpired):pass
    if time.monotonic()-start>=notice:
        event('waiting_for_wireless_android',elapsed_seconds=round(time.monotonic()-start,1));notice+=30
    time.sleep(3)
else:raise TimeoutError('Wireless Android boot not observed; no further writes performed')
