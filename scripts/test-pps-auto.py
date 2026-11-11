#!/usr/bin/env python3
"""Exercise production PPS policy, snapshots, worker and manual store with fault injection."""
from pathlib import Path
import json
import os
import re
import subprocess

workspace=Path(os.environ['PROJECT_ROOT']).resolve()
(workspace/'dist'/os.environ['TAG']/'host-tests').mkdir(parents=True,exist_ok=True)
project=workspace
base=Path(os.environ['BUILD_ROOT'])/'k618/soc/drivers/power/supply'
source=(base/'qti_battery_charger.c').read_text()
enums='\n'.join(m[0] for m in re.finditer(r'enum\s+\w+\s*\{[^{}]*\};',source)
    if any(token in m[0] for token in ('PSY_TYPE_BATTERY','BATT_HEALTH','USB_ONLINE','XM_PROP_PD_VERIFED')))
manual=re.search(r'static ssize_t pd_verifed_store\([^{}]*\)\s*\{.*?^\}',source,re.M|re.S)[0]
verify_manual=re.search(r'static ssize_t verify_process_store\([^{}]*\)\s*\{.*?^\}',source,re.M|re.S)[0]
shim=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
typedef uint32_t u32;
#define HZ 1000UL
#define time_before(a,b) ((long)((a)-(b))<0)
#define READ_ONCE(x) (x)
#define module_param_named(a,b,c,d)
#define MODULE_PARM_DESC(a,b)
#define PMIC_GLINK_STATE_UP 1
#define POWER_SUPPLY_USB_TYPE_PD_PPS 9
#define POWER_SUPPLY_HEALTH_GOOD 1
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
struct work_struct {int dummy;};
struct delayed_work {struct work_struct work;};
struct class {int dummy;};
struct class_attribute {int dummy;};
#define to_delayed_work(p) container_of(p,struct delayed_work,work)
#define system_freezable_wq ((void *)1)
#define dev_info(dev,fmt,...) ((void)(dev))
#define dev_warn(dev,fmt,...) ((void)(dev))
static int atomic_read(int *p){return *p;}
static void atomic_inc(int *p){++*p;}
static int atomic_xchg(int *p,int v){int old=*p;*p=v;return old;}
static void mutex_lock(int *p){assert(*p==0);*p=1;}
static void mutex_unlock(int *p){assert(*p==1);*p=0;}
static int scheduled,notifications;
static unsigned long last_delay;
static int mod_delayed_work(void *q,struct delayed_work *w,unsigned long delay){
    (void)q;(void)w;++scheduled;last_delay=delay;return 1;
}
#define queue_delayed_work mod_delayed_work
static void schedule_delayed_work(struct delayed_work *w,unsigned long delay){(void)w;(void)delay;++notifications;}
static void power_supply_changed(void *p){assert(p);++notifications;}
static int kstrtobool(const char *s,bool *v){
    if(!strcmp(s,"1")){*v=true;return 0;}if(!strcmp(s,"0")){*v=false;return 0;}return -EINVAL;
}
'''
structs=r'''
struct psy_state {u32 prop[233];void *psy;};
struct battery_chg_dev {
    int state,sheng_pps_epoch,sheng_pps_reset,sheng_pps_lock;
    bool sheng_pps_stopping,debug_battery_detected,block_tx;
    struct class battery_class;
    struct delayed_work sheng_pps_work,xm_prop_change_work;
    struct sheng_pps_policy sheng_pps;
    struct psy_state psy_list[PSY_TYPE_MAX];
    void *dev;
};
static int reads,writes,remote_rc,write_rc,ack_one=1;
static int drop_at,notify_at,native_at,disable_at,unplug_on_write;
static bool sheng_pps_auto_verify;
static int read_property_id(struct battery_chg_dev *b,struct psy_state *p,u32 id){
    assert(b->sheng_pps_lock==1 && id<233);(void)p;++reads;
    if(reads==drop_at)b->state=0;
    if(reads==notify_at)++b->sheng_pps_epoch;
    if(reads==native_at)b->psy_list[PSY_TYPE_USB].prop[USB_REAL_TYPE]=2;
    if(reads==disable_at)sheng_pps_auto_verify=false;
    return remote_rc;
}
static int write_property_id(struct battery_chg_dev *b,struct psy_state *p,u32 id,u32 v){
    assert(b->sheng_pps_lock==1 && p==&b->psy_list[PSY_TYPE_XM] && (id==XM_PROP_PD_VERIFED || id==XM_PROP_VERIFY_PROCESS) && v<=1);
    ++writes;if(write_rc)return write_rc;
    if(ack_one)p->prop[id]=v;
    if(unplug_on_write)b->psy_list[PSY_TYPE_USB].prop[USB_ONLINE]=0;
    return 0;
}
'''
# The parameter has a forward declaration in the shim to permit injected disabling.
worker=(base/'sheng_pps_auto_verify.h').read_text()
assert 'static bool sheng_pps_auto_verify = true;' in worker
worker=worker.replace('static bool sheng_pps_auto_verify = true;',
    '/* Declaration supplied before transport shims; reset() sets the production default. */')
main=r'''
static void reset(struct battery_chg_dev *b){
    memset(b,0,sizeof(*b));b->state=1;b->dev=b;
    b->psy_list[PSY_TYPE_USB].psy=b;
    b->psy_list[PSY_TYPE_USB].prop[USB_ONLINE]=1;
    b->psy_list[PSY_TYPE_USB].prop[USB_REAL_TYPE]=POWER_SUPPLY_USB_TYPE_PD_PPS;
    b->psy_list[PSY_TYPE_BATTERY].prop[BATT_HEALTH]=POWER_SUPPLY_HEALTH_GOOD;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_AUTHENTIC]=1;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_SLAVE_AUTHENTIC]=1;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_BATTERY_ADAPT_POWER_MATCH]=1;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0x12d1;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=90;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_POWER_MAX]=90;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_CURRENT_STATE]=31;
    reads=writes=scheduled=notifications=remote_rc=write_rc=0;ack_one=1;
    drop_at=notify_at=native_at=disable_at=unplug_on_write=0;
    sheng_pps_auto_verify=true;
}
static void run(struct battery_chg_dev *b){sheng_pps_auto_work(&b->sheng_pps_work.work);assert(b->sheng_pps_lock==0);}
static void prime(struct battery_chg_dev *b){reset(b);}
int main(void){
    struct battery_chg_dev b;struct sheng_pps_policy p={0};
    struct sheng_pps_sample s={.online=true,.pps=true,.ready=true,.healthy=true,.authenticated=true,.svid=0x12d1,.apdo_watts=90,.power_watts=90};
    assert(sheng_pps_decide(&p,&s)==SHENG_PPS_UNLOCK);
    s.verifying=true;assert(sheng_pps_decide(&p,&s)==SHENG_PPS_BLOCKED);s.verifying=false;
    s.adapter_id=1;assert(sheng_pps_decide(&p,&s)==SHENG_PPS_NATIVE);s.adapter_id=0;
    p.attempts=3;s.online=false;assert(sheng_pps_decide(&p,&s)==SHENG_PPS_OFFLINE && !p.attempts);
    prime(&b);run(&b);assert(writes==1 && notifications==2 && last_delay==5*HZ && !b.sheng_pps.attempts);
    run(&b);assert(writes==1); /* existing one is monitored but never rewritten */
    /* Repeated firmware clears do not consume the successful-write budget. */
    for(int i=0;i<8;i++){b.psy_list[PSY_TYPE_XM].prop[XM_PROP_PD_VERIFED]=0;run(&b);}
    assert(writes==9 && !b.sheng_pps.attempts);
    /* Actual batterysecret sequence: verify1 -> verify0 -> sysfs0 -> immediate restore. */
    assert(verify_process_store(&b.battery_class,NULL,"1",1)==1 && b.sheng_pps_epoch==1 && last_delay==0);
    assert(pd_verifed_store(&b.battery_class,NULL,"0",1)==1 && last_delay==0);
    writes=0;run(&b);assert(!writes);
    assert(verify_process_store(&b.battery_class,NULL,"0",1)==1 && b.sheng_pps_epoch==2 && last_delay==0);
    assert(pd_verifed_store(&b.battery_class,NULL,"0",1)==1 && last_delay==0);
    writes=0;run(&b);assert(writes==1);
    /* Disabling automatic mode keeps a manual zero; no replug required. */
    sheng_pps_auto_verify=false;assert(pd_verifed_store(&b.battery_class,NULL,"0",1)==1);
    writes=0;reads=0;run(&b);assert(!writes && !reads);
    reset(&b);b.psy_list[PSY_TYPE_USB].prop[USB_ONLINE]=0;run(&b);assert(!writes && !scheduled && !b.sheng_pps.connected);
    reset(&b);b.psy_list[PSY_TYPE_USB].prop[USB_REAL_TYPE]=2;run(&b);assert(!writes && !scheduled);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_PD_VERIFED]=1;run(&b);assert(!writes && reads==3);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0x2717;b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_ID]=0xa819;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0x2717;b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=90;run(&b);assert(writes==1); /* captured Huawei */
    for(int svid=0;svid<=1;svid++){
        reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=svid?0x2717:0;
        b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=100;run(&b);assert(!writes);
        b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=120;run(&b);assert(!writes);
        b.psy_list[PSY_TYPE_XM].prop[XM_PROP_PD_VERIFED]=1;run(&b);assert(!writes);
    }
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_CURRENT_STATE]=25;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_VERIFY_PROCESS]=1;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0;b.psy_list[PSY_TYPE_XM].prop[XM_PROP_POWER_MAX]=100;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0x291a;b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=140;run(&b);assert(writes==1);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=0;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_SLAVE_AUTHENTIC]=0;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_AUTHENTIC]=0;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_BATTERY_ADAPT_POWER_MATCH]=0;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_BATTERY].prop[BATT_HEALTH]=2;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_INPUT_SUSPEND]=1;run(&b);assert(!writes);
    prime(&b);drop_at=14;run(&b);assert(!writes && !notifications);
    prime(&b);native_at=14;run(&b);assert(!writes && !notifications);
    prime(&b);notify_at=14;run(&b);assert(!writes && !notifications && last_delay==0);
    prime(&b);disable_at=14;run(&b);assert(!writes && !notifications);
    prime(&b);unplug_on_write=1;run(&b);assert(writes==1 && !notifications);
    prime(&b);write_rc=-EIO;run(&b);run(&b);run(&b);run(&b);assert(writes==3 && b.sheng_pps.attempts==3 && !notifications);
    prime(&b);ack_one=0;run(&b);run(&b);run(&b);run(&b);assert(writes==3 && !notifications);
    reset(&b);remote_rc=-ETIMEDOUT;run(&b);run(&b);run(&b);assert(!writes && b.sheng_pps.attempts==3);
    reset(&b);b.state=0;run(&b);assert(!reads && !writes && !scheduled);
    reset(&b);b.debug_battery_detected=b.block_tx=true;run(&b);assert(!reads && !writes);
    reset(&b);b.sheng_pps_stopping=true;run(&b);sheng_pps_kick(&b);assert(!reads && !writes && !scheduled);
    prime(&b);b.sheng_pps.attempts=3;b.sheng_pps_reset=1;run(&b);assert(writes==1 && !b.sheng_pps.attempts);
    assert(pd_verifed_store(&b.battery_class,NULL,"bad",3)==-EINVAL);
    b.state=0;assert(pd_verifed_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);
    puts("r87 production PPS policy/worker/store: batterysecret zero recovery, native100->120 priority, immediate events, verified monitoring, repeated clears, protection gates and bounded consecutive failures passed");
    return 0;
}
'''
folder=project/'dist'/os.environ['TAG']/'host-tests'/ 'pps-auto';folder.mkdir(parents=True,exist_ok=True)
(folder/'test.c').write_text(shim+enums+(base/'sheng_pps_policy.h').read_text()+structs+worker+manual+verify_manual+main)
result=subprocess.run(['cc','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',
    '-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-function','-Wno-misleading-indentation',
    str(folder/'test.c'),'-o',str(folder/'test')],capture_output=True,text=True)
(folder/'compile.log').write_text(result.stdout+result.stderr)
if result.returncode:print(result.stderr,flush=True);raise SystemExit(result.returncode)
result=subprocess.run([str(folder/'test')],capture_output=True,text=True)
(folder/'run.log').write_text(result.stdout+result.stderr)
assert result.returncode==0,result.stderr
report=dict(passed=True,production_callbacks_tested=['policy','snapshot','worker','manual_store','verify_process_store'],
    stable_grace_seconds=0,sanitizers='ASan/UBSan',hardware_verified=False,
    coverage=['immediate first eligible snapshot without scheduled delay','native Xiaomi/power/ambiguous ID priority',
        'real Huawei baseline with retained Xiaomi SVID and zero ID','SNK_Startup versus SNK_Ready',
        'existing one unchanged','battery authentication/health/input-suspend gates',
        'fresh source/glink/notification/disable races','no success on post-write unplug',
        '3 consecutive failures; successful repeated clears reset budget','batterysecret zero immediately rechecked; N preserves manual zero','glink reset and removal'],
    limitation='Firmware/workqueue/parser/mutex host shims; real adapter timing and Xiaomi/Huawei charging still require device tests')
(workspace/('dist/'+os.environ['TAG']+'/host-tests/')/'kernel618-pps-auto-r87-tests.json').write_text(json.dumps(report,indent=2)+'\n')
print(result.stdout,flush=True);print(json.dumps(report),flush=True)
