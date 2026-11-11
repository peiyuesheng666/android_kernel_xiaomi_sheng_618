#!/usr/bin/env python3
"""Exercise production scalar charger callbacks and bypass error paths on host."""
from pathlib import Path
import json
import os
import subprocess

workspace=Path(os.environ['PROJECT_ROOT']).resolve()
(workspace/'dist'/os.environ['TAG']/'host-tests').mkdir(parents=True,exist_ok=True)
project=workspace
build=Path(os.environ['BUILD_ROOT']).resolve()
receipt=json.loads((project/'provenance/repair-r85.json').read_text())
folder=project/'dist'/os.environ['TAG']/'host-tests'/ 'charging-callbacks';folder.mkdir(parents=True,exist_ok=True)
source=(build/'k618/soc/drivers/power/supply/qti_battery_charger.c').read_text()
bypass=source.split('/* Shipping sheng bypass control:',1)[1].split('static ssize_t fastchg_mode_show',1)[0]
bypass='/* Shipping sheng bypass control:'+bypass
callbacks=(build/'k618/soc/drivers/power/supply/sheng_charging_interfaces.h').read_text()+bypass
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
#define PAGE_SIZE 4096
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define scnprintf snprintf
#define READ_ONCE(x) (x)
#define atomic_read(p) (*(p))
#define PMIC_GLINK_STATE_UP 1
#define PSY_TYPE_XM 0
#define XM_PROP_CHARGING_SUSPEND_BATTERY 219
#define CLASS_ATTR_RW(name) struct class_attribute class_attr_##name __attribute__((unused)) = {0}
#define CLASS_ATTR_RO(name) CLASS_ATTR_RW(name)
struct class { int padding; };
struct class_attribute { int padding; };
struct psy_state { u32 prop[233]; };
struct battery_chg_dev { int state; bool debug_battery_detected, block_tx;
    struct class battery_class; struct psy_state psy_list[1]; };
static int remote_rc, attempts, last_id, drop_after;
static u32 last_value;
static int read_property_id(struct battery_chg_dev *b, struct psy_state *p,u32 id) {
    assert(id<233); ++attempts; last_id=id; if(drop_after)b->state=0; return remote_rc;
}
static int write_property_id(struct battery_chg_dev *b, struct psy_state *p,u32 id,u32 value) {
    assert(id<233); ++attempts;last_id=id;last_value=value;if(drop_after)b->state=0;return remote_rc;
}
static int kstrtobool(const char *s,bool *v) {
    if (!strcmp(s,"1") || !strcmp(s,"true")) {*v=true;return 0;}
    if (!strcmp(s,"0") || !strcmp(s,"false")) {*v=false;return 0;}
    return -EINVAL;
}
static int kstrtoint(const char *s,int base,int *v) {
    char *end;errno=0;long x=strtol(s,&end,base);
    if(errno || end==s || *end || x>INT_MAX || x<INT_MIN)return -EINVAL;
    *v=x;return 0;
}
static int kstrtouint(const char *s,int base,unsigned int *v) {
    char *end;errno=0;unsigned long x=strtoul(s,&end,base);
    if(errno || end==s || *end || *s=='-' || x>UINT_MAX)return -EINVAL;
    *v=x;return 0;
}
'''
rows=receipt['restored_scalar_nodes']+[dict(node='charging_suspend_battery',id=219,format='%u\n',parser='kstrtobool')]
main='int main(void) { struct battery_chg_dev b={.state=1}; char out[4096],expected[4096]; int before;\n'
for row in rows:
    name,prop=row['node'],row['id'];fmt=json.dumps(row['format'])
    main+=f'''b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[{prop}]=17;
    snprintf(expected,sizeof(expected),{fmt},17);
    assert({name}_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id=={prop});
    remote_rc=-ETIMEDOUT;assert({name}_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert({name}_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert({name}_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert({name}_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
'''
    if row['parser']:
        main+=f'''remote_rc=0;assert({name}_store(&b.battery_class,NULL,"1",1)==1 && last_id=={prop} && last_value==1);
        assert({name}_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert({name}_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert({name}_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert({name}_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert({name}_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
'''
        if row['parser']!='kstrtobool':
            main+=f'''before=attempts;assert({name}_store(&b.battery_class,NULL,"4294967296",10)==-EINVAL && before==attempts);
'''
main+='puts("Production callbacks: read/write IDs, formats, invalid input, overflow and glink error paths passed");return 0;}\n'
(folder/'test.c').write_text(shim+callbacks+main)
subprocess.run(['cc','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-Wall','-Wextra',
    '-Wno-unused-parameter','-Wno-unused-function','-Werror',str(folder/'test.c'),'-o',str(folder/'test')],check=True)
result=subprocess.run([str(folder/'test')],capture_output=True,text=True,check=True)
print(result.stdout,flush=True)
report=dict(production_callbacks_tested=len(rows),writable_callbacks=sum(bool(r['parser']) for r in rows),
    sanitizer='ASan/UBSan',passed=True,runtime_verified=False,
    coverage=['property IDs','signed/unsigned output formats','invalid parsers','overflow','remote errors',
              'glink down before and after transaction','blocked transport'],
    limitation='Host firmware and parser shims; hardware charging and kernel lifecycle remain unverified')
(workspace/('dist/'+os.environ['TAG']+'/host-tests/')/'kernel618-charging-interfaces-r85-tests.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
