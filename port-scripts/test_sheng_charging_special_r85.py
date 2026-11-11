#!/usr/bin/env python3
"""Exercise actual special callbacks, message decoding and bounded factory polling."""
from pathlib import Path
import json
import re
import subprocess

workspace=Path(__file__).resolve().parents[1]
project=Path('/root/sheng-618-repair-r85-project');build=Path('/root/sheng-618-repair-r85-build')
folder=project/'tests/charging-special';folder.mkdir(parents=True,exist_ok=True)
base=build/'k618/soc/drivers/power/supply'
source=(base/'qti_battery_charger.c').read_text()
fw=re.search(r'static ssize_t wireless_chip_fw_show\([^{}]*\)\s*\{.*?^\}',source,re.M|re.S)[0]
shim=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <sys/types.h>
typedef uint32_t u32;
#undef static_assert
#define static_assert(x) _Static_assert(x,#x)
#define PAGE_SIZE 4096
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define scnprintf snprintf
#define READ_ONCE(x) (x)
#define atomic_read(p) (*(p))
#define PMIC_GLINK_STATE_UP 1
#define PSY_TYPE_XM 0
#define MSG_OWNER_BC 32778
#define MSG_TYPE_REQ_RESP 1
#define BC_XM_STATUS_GET 0x50
#define XM_PROP_FW_VER 72
#define WIRELESS_CHIP_FW_VERSION_LEN 16
#define GFP_KERNEL 0
#define CLASS_ATTR_RW(n) struct class_attribute class_attr_##n __attribute__((unused))={0}
#define CLASS_ATTR_RO(n) CLASS_ATTR_RW(n)
struct class { int padding; };
struct class_attribute { int padding; };
struct pmic_glink_hdr { u32 owner,type,opcode; };
struct psy_state { u32 prop[233]; u32 opcode_get; };
struct battery_chg_dev { int state; bool debug_battery_detected,block_tx;
    struct class battery_class; struct psy_state psy_list[1];
    char sheng_battery_serial[49],sheng_wireless_uuid[25],wireless_chip_fw_version[16]; };
struct wireless_chip_fw_msg { struct pmic_glink_hdr hdr; u32 property_id,value; char version[16]; };
static int remote_rc,last_id,calls,allocations,fail_alloc,drop_after;
static u32 last_value;
static unsigned long jiffies;
static const char *fw_value="12.34.56.78";
static unsigned long msecs_to_jiffies(unsigned int n) { return n; }
static bool time_after_eq(unsigned long a,unsigned long b) {return a>=b;}
static void msleep(unsigned int n) {jiffies+=n;}
static void *kzalloc(size_t n,int flags) {if(fail_alloc)return NULL;++allocations;return calloc(1,n);}
static void kfree(void *p) {assert(allocations>0);--allocations;free(p);}
static int read_property_id(struct battery_chg_dev *b,struct psy_state *p,u32 id) {
    assert(id<233);last_id=id;++calls;if(drop_after)b->state=0;return remote_rc;
}
static int write_property_id(struct battery_chg_dev *b,struct psy_state *p,u32 id,u32 value) {
    assert(id<233);last_id=id;last_value=value;++calls;return remote_rc;
}
static int kstrtobool(const char *s,bool *v) {
    if(!strcmp(s,"1")){*v=true;return 0;}if(!strcmp(s,"0")){*v=false;return 0;}return -EINVAL;
}
static int kstrtoint(const char *s,int base,int *v) {
    char *end;errno=0;long x=strtol(s,&end,base);
    if(errno||end==s||*end||x>INT_MAX||x<INT_MIN)return -EINVAL;*v=x;return 0;
}
static int kstrtouint(const char *s,int base,unsigned int *v) {
    char *end;errno=0;unsigned long x=strtoul(s,&end,base);
    if(errno||end==s||*end||*s=='-'||x>UINT_MAX)return -EINVAL;*v=x;return 0;
}
'''
messages=(base/'sheng_charging_messages.h').read_text()
decoder=(base/'sheng_charging_message_decode.h').read_text()
transport=r'''
static int battery_chg_write(struct battery_chg_dev *b,void *data,int len) {
    struct sheng_battery_serial_msg *request=data;
    assert(request->hdr.owner==MSG_OWNER_BC && request->hdr.type==MSG_TYPE_REQ_RESP && request->hdr.opcode==BC_XM_STATUS_GET);
    ++calls;last_id=request->property_id;if(remote_rc)return remote_rc;
    if(len==64){
        assert(request->property_id==160);struct sheng_battery_serial_msg reply={.hdr={.opcode=BC_XM_STATUS_GET},.property_id=160};
        memset(reply.serial,'S',48);assert(sheng_charging_decode_text(b,&reply,sizeof(reply)));
    }else if(len==44){
        assert(request->property_id==73);struct sheng_wireless_uuid_msg reply={.hdr={.opcode=BC_XM_STATUS_GET},.property_id=73};
        memset(reply.version,'U',24);assert(sheng_charging_decode_text(b,&reply,sizeof(reply)));
    }else if(len==36){
        assert(request->property_id==72);memset(b->wireless_chip_fw_version,0,16);
        memcpy(b->wireless_chip_fw_version,fw_value,strlen(fw_value));
    }else assert(false);
    if(drop_after)b->state=0;return 0;
}
'''
callbacks=(base/'sheng_charging_interfaces.h').read_text()+fw+(base/'sheng_charging_special.h').read_text()
main=r'''
int main(void) {
    struct battery_chg_dev b={.state=1};b.psy_list[0].opcode_get=BC_XM_STATUS_GET;
    char out[4096];int before;
    assert(batt_sn_show(&b.battery_class,NULL,out)==49 && last_id==160);
    assert(out[48]=='\n' && out[49]==0 && b.sheng_battery_serial[48]==0);
    assert(wireless_tx_uuid_show(&b.battery_class,NULL,out)==25 && last_id==73);
    assert(out[24]=='\n' && b.sheng_wireless_uuid[24]==0);
    struct sheng_battery_serial_msg serial={.hdr={.opcode=BC_XM_STATUS_GET},.property_id=160};
    struct sheng_wireless_uuid_msg uuid={.hdr={.opcode=BC_XM_STATUS_GET},.property_id=73};
    for(size_t n=0;n<sizeof(serial);++n)assert(!sheng_charging_decode_text(&b,&serial,n));
    for(size_t n=0;n<sizeof(uuid);++n)assert(!sheng_charging_decode_text(&b,&uuid,n));
    serial.hdr.opcode=0x51;assert(!sheng_charging_decode_text(&b,&serial,sizeof(serial)));
    uuid.property_id=74;assert(!sheng_charging_decode_text(&b,&uuid,sizeof(uuid)));
    remote_rc=-ETIMEDOUT;
    assert(batt_sn_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    assert(wireless_tx_uuid_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    assert(battery_param_reset_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=calls;
    assert(batt_sn_show(&b.battery_class,NULL,out)==-ENOTCONN && before==calls);
    assert(wireless_tx_uuid_show(&b.battery_class,NULL,out)==-ENOTCONN && before==calls);
    b.state=1;drop_after=1;
    assert(batt_sn_show(&b.battery_class,NULL,out)==-ENOTCONN);
    b.state=1;assert(wireless_tx_uuid_show(&b.battery_class,NULL,out)==-ENOTCONN);
    b.state=1;drop_after=0;
    assert(battery_param_reset_show(&b.battery_class,NULL,out)==4 && !strcmp(out,"100\n") && last_id==113);
    assert(battery_param_reset_store(&b.battery_class,NULL,"1",1)==1 && last_id==113 && last_value==1);
    before=calls;assert(battery_param_reset_store(&b.battery_class,NULL,"-1",2)==-EINVAL && before==calls);
    assert(battery_param_reset_store(&b.battery_class,NULL,"4294967296",10)==-EINVAL && before==calls);
    b.psy_list[0].prop[223]=1;assert(car_app_show(&b.battery_class,NULL,out)==1 && !strcmp(out,"1") && last_id==223);
    fail_alloc=1;assert(wireless_version_forcit_show(&b.battery_class,NULL,out)==-ENOMEM && allocations==0);fail_alloc=0;
    fw_value="12.34.56.78";assert(wireless_version_forcit_show(&b.battery_class,NULL,out)==5 && !strcmp(out,"pass\n") && allocations==0);
    fw_value="00.00.00.00";assert(wireless_version_forcit_show(&b.battery_class,NULL,out)==5 && !strcmp(out,"fail\n") && allocations==0);
    fw_value="12.fe.56.78";assert(wireless_version_forcit_show(&b.battery_class,NULL,out)==5 && !strcmp(out,"fail\n") && allocations==0);
    fw_value="updating";jiffies=0;assert(wireless_version_forcit_show(&b.battery_class,NULL,out)==-ETIMEDOUT && jiffies==5000 && allocations==0);
    fw_value="";assert(wireless_version_forcit_show(&b.battery_class,NULL,out)==-ENODATA && allocations==0);
    fw_value="\n";assert(wireless_version_forcit_show(&b.battery_class,NULL,out)==-ENODATA && allocations==0);
    fw_value="12.34.56.78";drop_after=1;
    assert(wireless_version_forcit_show(&b.battery_class,NULL,out)==-ENOTCONN && allocations==0);
    b.state=1;drop_after=0;
    remote_rc=-EIO;assert(wireless_version_forcit_show(&b.battery_class,NULL,out)==-EINVAL && allocations==0);
    puts("Production special callbacks: message lengths/IDs, non-NUL payloads, malformed replies, errors, OOM and bounded factory polling passed");
    return 0;
}
'''
(folder/'test.c').write_text(shim+messages+decoder+transport+callbacks+main.replace(r'\\n',r'\n'))
compiled=subprocess.run(['cc','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-Wall','-Wextra',
    '-Wno-unused-parameter','-Wno-unused-function','-Wno-misleading-indentation','-Werror',
    '-Wno-missing-field-initializers',str(folder/'test.c'),'-o',str(folder/'test')],capture_output=True,text=True)
(folder/'compile.log').write_text(compiled.stdout+compiled.stderr)
if compiled.returncode:
    print('\n'.join(compiled.stderr.splitlines()[-30:]),flush=True)
    raise SystemExit(compiled.returncode)
result=subprocess.run([str(folder/'test')],capture_output=True,text=True,check=True)
print(result.stdout,flush=True)
report=dict(production_special_callbacks=5,passed=True,sanitizers='ASan/UBSan',hardware_verified=False,
    coverage=['64/44 byte requests','property IDs 160/73/113/223/72','non-NUL 48/24-byte replies',
              'wrong opcode/property and all truncated lengths','transport errors','glink disconnect',
              'factory allocation failure','factory polling timeout and buffer cleanup',
              'factory empty/newline version rejection','factory disconnect during read'],
    limitation='Host firmware/parser/allocation shims; actual device responses and concurrent access remain to verify')
(workspace/'reports/kernel618-charging-special-r85-tests.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
