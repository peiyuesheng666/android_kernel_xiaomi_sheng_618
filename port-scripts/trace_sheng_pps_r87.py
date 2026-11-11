"""Own a private trace instance; record only charging store flags, never auth data."""
from pathlib import Path
import json
import subprocess
import sys
import time

w=Path(__file__).resolve().parents[1]
adb=[str(w/'tools/platform-tools/adb.exe'),'-s','192.168.1.14:5555']
root='/sys/kernel/tracing'
instance=root+'/instances/sheng_pps_r87'
group='sheng_pps_r87'
def shell(cmd,check=True):
    wrapped="su -c '"+cmd.replace("'","'\"'\"'")+"'"
    r=subprocess.run(adb+['shell',wrapped],capture_output=True,timeout=20)
    if check and r.returncode:raise RuntimeError((r.stdout+r.stderr).decode(errors='replace'))
    return r.stdout.decode(errors='replace').strip()
assert subprocess.check_output(adb+['shell','getprop ro.serialno']).decode().strip()=='603ac302'
mode=sys.argv[1]
if mode=='start':
    assert not shell('test -e '+instance+' && echo exists',False)
    existing=shell('cat '+root+'/kprobe_events')
    assert group+'/' not in existing
    shell('mkdir '+instance)
    for event,symbol in [('pd_store','pd_verifed_store'),('verify_store','verify_process_store')]:
        probe='p:'+group+'/'+event+' qti_battery_charger:'+symbol+' value=+0(%x2):u8'
        shell('echo "'+probe+'" >> '+root+'/kprobe_events')
        shell('echo 1 > '+instance+'/events/'+group+'/'+event+'/enable')
    shell('echo 1 > '+instance+'/tracing_on')
    print('Private charging flag trace active')
elif mode=='read':
    folder=w/'logs'/('pps-r87-trace-'+time.strftime('%Y%m%d-%H%M%S'));folder.mkdir()
    data=shell('cat '+instance+'/trace')
    (folder/'trace.txt').write_text(data+'\n',encoding='utf-8')
    state={n:shell('cat /sys/class/qcom-battery/'+n) for n in
           ['pd_verifed','verify_process','adapter_svid','adapter_id','apdo_max','power_max','current_state']}
    state['online']=shell('cat /sys/class/power_supply/usb/online')
    (folder/'state.json').write_text(json.dumps(state,indent=2)+'\n')
    print(data[-12000:]);print(json.dumps(state));print(folder)
elif mode=='stop':
    shell('echo 0 > '+instance+'/tracing_on')
    for event in ['pd_store','verify_store']:
        shell('echo 0 > '+instance+'/events/'+group+'/'+event+'/enable')
        shell('echo "-:'+group+'/'+event+'" >> '+root+'/kprobe_events')
    shell('rmdir '+instance)
    print('Removed only the private charging trace')
