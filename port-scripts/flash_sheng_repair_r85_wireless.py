#!/usr/bin/env python3
"""Flash only the verified r85 boot_a to 603ac302 over wireless root ADB."""
from pathlib import Path
import hashlib
import json
import subprocess
import time

workspace = Path(__file__).resolve().parents[1]
address = '192.168.1.14:5555'
serial = '603ac302'
delivery = workspace/'artifacts/sheng-6.18-repair-r85'
image = delivery/'boot.img'
rollback = workspace/'artifacts/sheng-6.18-qcom-walt-classic-r80/boot.img'
before_sha = 'ef96897939a4e8b0a6ab8675cc88e438180f249bd531f340c8b25c54bc416137'
init_sha = '8d917a47bed84e8f7a0c8ab36a997523ad41157d10afc2222a52184b68ecfae2'
size = 201326592
adb = str(workspace/'tools/platform-tools/adb.exe')
report_path = workspace/'reports/kernel618-repair-r85-wireless-flash.json'
assert not report_path.exists(), 'Preserve the existing flash record'
backup = workspace/'backups'/('sheng-r85-wireless-'+time.strftime('%Y%m%d-%H%M%S'))
backup.mkdir()
state = dict(serial=serial,address=address,revision='repair-r85',writes=['boot_a'],events=[],
             backup_directory=str(backup),transport='wireless ADB',usb_used=False)
def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()
def event(name,**fields):
    state['events'].append(dict(event=name,**fields))
    report_path.write_text(json.dumps(state,indent=2)+'\n')
    print(json.dumps(state['events'][-1]),flush=True)
def call(*args,timeout=30):
    p=subprocess.run([adb,'-s',address,*map(str,args)],capture_output=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError((p.stdout+p.stderr).decode(errors='replace'))
    return p.stdout.decode(errors='replace').strip()
def shell(command,root=False,timeout=30):
    if root:command="su -c '"+command.replace("'","'\"'\"'")+"'"
    return call('shell',command,timeout=timeout)
def device_sha(path):return shell('sha256sum '+path,True,timeout=90).split()[0]
def identity():
    assert shell('getprop ro.serialno')==serial
    assert shell('getprop ro.boot.slot_suffix')=='_a'
try:
    validation=json.loads((delivery/'validation.json').read_text())
    package=json.loads((delivery/'package-validation.json').read_text())
    assert validation['fresh_build_verified'] and validation['module_abi']['abi_passed']
    assert validation['build_profile']['mode']=='release' and not validation['build_profile']['rawdump_enabled']
    assert package['patch_replay_verified'] and package['archive_readback_verified']
    assert sha(image)==package['boot_sha256']==validation['build']['artifacts']['boot.img']
    assert sha(rollback)==before_sha and rollback.stat().st_size==image.stat().st_size==size
    identity()
    assert shell('getprop sys.boot_completed')=='1'
    assert shell('id -u',True)=='0'
    battery=shell('cat /sys/class/power_supply/battery/capacity')
    assert int(battery)>=30
    assert shell('test ! -e /data/adb/modules/sheng_adb_5555/disable && test ! -e /data/adb/modules/sheng_adb_5555/remove && test -s /data/adb/modules/sheng_adb_5555/service.sh && echo ready',True)=='ready'
    assert device_sha('/dev/block/by-name/boot_a')==before_sha
    assert device_sha('/dev/block/by-name/init_boot_a')==init_sha
    assert shell('blockdev --getsize64 /dev/block/by-name/boot_a',True)==str(size)
    state.update(image_sha256=sha(image),rollback_sha256=before_sha,init_boot_before_sha256=init_sha,
                 boot_id_before=shell('cat /proc/sys/kernel/random/boot_id'),battery_capacity_before=battery)
    # Save a fresh read of the active partition locally, independently of the old artifact.
    remote_backup='/data/local/tmp/sheng-before-r85-boot-a.img'
    shell('dd if=/dev/block/by-name/boot_a of='+remote_backup+' bs=4M && sync',True,timeout=90)
    assert device_sha(remote_backup)==before_sha
    call('pull',remote_backup,backup/'boot_a.img',timeout=180)
    assert sha(backup/'boot_a.img')==before_sha
    (backup/'preflight.json').write_text(json.dumps(state,indent=2)+'\n')
    event('identity_slot_partition_init_boot_and_fresh_backup_verified')
    remote='/data/local/tmp/sheng-repair-r85-boot.img'
    call('push',image,remote,timeout=180)
    assert device_sha(remote)==state['image_sha256']
    assert shell('stat -c %s '+remote,True)==str(size)
    identity()
    assert device_sha('/dev/block/by-name/boot_a')==before_sha
    event('candidate_uploaded_and_remote_hash_verified')
    shell('dd if='+remote+' of=/dev/block/by-name/boot_a bs=4M conv=fsync && sync',True,timeout=90)
    event('boot_a_write_completed')
    if device_sha('/dev/block/by-name/boot_a')!=state['image_sha256']:
        shell('dd if='+remote_backup+' of=/dev/block/by-name/boot_a bs=4M conv=fsync && sync',True,timeout=90)
        assert device_sha('/dev/block/by-name/boot_a')==before_sha
        raise RuntimeError('Candidate readback failed; verified previous boot restored before reboot')
    assert device_sha('/dev/block/by-name/init_boot_a')==init_sha
    event('full_partition_readback_verified')
    shell('reboot',True)
    start=time.monotonic();notice=0
    while time.monotonic()-start<240:
        try:
            subprocess.run([adb,'connect',address],capture_output=True,timeout=5)
            if shell('getprop sys.boot_completed',timeout=5)=='1':
                identity()
                boot_id=shell('cat /proc/sys/kernel/random/boot_id')
                if boot_id!=state['boot_id_before']:
                    assert device_sha('/dev/block/by-name/boot_a')==state['image_sha256']
                    assert device_sha('/dev/block/by-name/init_boot_a')==init_sha
                    state.update(boot_id_after=boot_id,uname=shell('uname -a'),cmdline=shell('cat /proc/cmdline'))
                    assert 'sheng_bootlog' not in state['cmdline']
                    assert shell('cat /sys/module/nt36532_touch/parameters/sheng_pen_contact_hold_ms')=='32'
                    event('android_boot_and_wireless_reconnect_verified',elapsed_seconds=round(time.monotonic()-start,1))
                    state['complete']=True;event('complete');break
        except (RuntimeError,subprocess.TimeoutExpired):pass
        if time.monotonic()-start>=notice:
            event('waiting_for_wireless_android',elapsed_seconds=round(time.monotonic()-start,1));notice+=30
        time.sleep(3)
    else:raise TimeoutError('Wireless Android boot not observed within 240 seconds; preserve backups')
except BaseException as error:
    event('failed',error=str(error));raise
