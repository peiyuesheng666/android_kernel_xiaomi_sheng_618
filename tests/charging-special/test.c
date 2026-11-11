
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
/* SPDX-License-Identifier: GPL-2.0-only */
/* Verified shipping requests: serial property 160 is 64 bytes, UUID 73 is 44 bytes. */
struct sheng_battery_serial_msg {
    struct pmic_glink_hdr hdr;
    u32 property_id;
    char serial[48];
};
struct sheng_wireless_uuid_msg {
    struct pmic_glink_hdr hdr;
    u32 property_id;
    u32 value;
    char version[24];
};
static_assert(sizeof(struct sheng_battery_serial_msg) == 64);
static_assert(sizeof(struct sheng_wireless_uuid_msg) == 44);
/* SPDX-License-Identifier: GPL-2.0-only */
static bool sheng_charging_decode_text(struct battery_chg_dev *bcdev,
        const void *data, size_t len)
{
    const struct sheng_battery_serial_msg *serial = data;
    const struct sheng_wireless_uuid_msg *uuid = data;
    if (len < sizeof(struct pmic_glink_hdr) + sizeof(u32))
        return false;
    if (serial->hdr.opcode != BC_XM_STATUS_GET)
        return false;
    if (len == sizeof(*serial) && serial->property_id == 160) {
        memcpy(bcdev->sheng_battery_serial, serial->serial, sizeof(serial->serial));
        bcdev->sheng_battery_serial[sizeof(serial->serial)] = '\0';
        return true;
    }
    if (len == sizeof(*uuid) && uuid->property_id == 73) {
        memcpy(bcdev->sheng_wireless_uuid, uuid->version, sizeof(uuid->version));
        bcdev->sheng_wireless_uuid[sizeof(uuid->version)] = '\0';
        return true;
    }
    return false;
}

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
/* SPDX-License-Identifier: GPL-2.0-only */
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

static ssize_t afp_temp_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 106, "%d\n", buf);
}
static CLASS_ATTR_RO(afp_temp);

static ssize_t battmoni_isc_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 114, "%d\n", buf);
}
static ssize_t battmoni_isc_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    int value;
    if (kstrtoint(buf, 0, &value))
        return -EINVAL;
    return sheng_charging_store(bcdev, 114, value, count);
}
static CLASS_ATTR_RW(battmoni_isc);

static ssize_t battmoni_soa_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 115, "%d\n", buf);
}
static CLASS_ATTR_RO(battmoni_soa);

static ssize_t blank_status_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 45, "%u\n", buf);
}
static ssize_t blank_status_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    bool value;
    if (kstrtobool(buf, &value))
        return -EINVAL;
    return sheng_charging_store(bcdev, 45, value, count);
}
static CLASS_ATTR_RW(blank_status);

static ssize_t cc_short_vbus_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 108, "%u", buf);
}
static ssize_t cc_short_vbus_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    int value;
    if (kstrtoint(buf, 0, &value))
        return -EINVAL;
    return sheng_charging_store(bcdev, 108, value, count);
}
static CLASS_ATTR_RW(cc_short_vbus);

static ssize_t charger_user_value_map_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 10, "%u", buf);
}
static ssize_t charger_user_value_map_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    int value;
    if (kstrtoint(buf, 0, &value))
        return -EINVAL;
    return sheng_charging_store(bcdev, 10, value, count);
}
static CLASS_ATTR_RW(charger_user_value_map);

static ssize_t cid_status_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 110, "%u", buf);
}
static CLASS_ATTR_RO(cid_status);

static ssize_t cloud_control_cid_mode_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 11, "%u", buf);
}
static ssize_t cloud_control_cid_mode_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    int value;
    if (kstrtoint(buf, 0, &value))
        return -EINVAL;
    return sheng_charging_store(bcdev, 11, value, count);
}
static CLASS_ATTR_RW(cloud_control_cid_mode);

static ssize_t cp_ovp_mode_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 221, "%u\n", buf);
}
static ssize_t cp_ovp_mode_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    bool value;
    if (kstrtobool(buf, &value))
        return -EINVAL;
    return sheng_charging_store(bcdev, 221, value, count);
}
static CLASS_ATTR_RW(cp_ovp_mode);

static ssize_t dam_ovpgate_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 218, "%u\n", buf);
}
static ssize_t dam_ovpgate_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    bool value;
    if (kstrtobool(buf, &value))
        return -EINVAL;
    return sheng_charging_store(bcdev, 218, value, count);
}
static CLASS_ATTR_RW(dam_ovpgate);

static ssize_t fg1_FullChargeFlag_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 181, "%d\n", buf);
}
static CLASS_ATTR_RO(fg1_FullChargeFlag);

static ssize_t fg1_ibatt_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 172, "%d\n", buf);
}
static CLASS_ATTR_RO(fg1_ibatt);

static ssize_t fg1_r1_discharge_flag_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 187, "%u\n", buf);
}
static CLASS_ATTR_RO(fg1_r1_discharge_flag);

static ssize_t fg1_r2_discharge_flag_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 188, "%u\n", buf);
}
static CLASS_ATTR_RO(fg1_r2_discharge_flag);

static ssize_t fg1_record_delta_r1_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 185, "%u\n", buf);
}
static CLASS_ATTR_RO(fg1_record_delta_r1);

static ssize_t fg1_record_delta_r2_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 186, "%u\n", buf);
}
static CLASS_ATTR_RO(fg1_record_delta_r2);

static ssize_t fg1_soc_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 183, "%u\n", buf);
}
static CLASS_ATTR_RO(fg1_soc);

static ssize_t fg1_temp_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 174, "%d\n", buf);
}
static CLASS_ATTR_RO(fg1_temp);

static ssize_t fg1_vol_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 176, "%u\n", buf);
}
static CLASS_ATTR_RO(fg1_vol);

static ssize_t fg2_FullChargeFlag_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 182, "%d\n", buf);
}
static CLASS_ATTR_RO(fg2_FullChargeFlag);

static ssize_t fg2_ai_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 178, "%d\n", buf);
}
static CLASS_ATTR_RO(fg2_ai);

static ssize_t fg2_current_max_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 169, "%d\n", buf);
}
static CLASS_ATTR_RO(fg2_current_max);

static ssize_t fg2_fcc_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 167, "%d\n", buf);
}
static CLASS_ATTR_RO(fg2_fcc);

static ssize_t fg2_ibatt_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 173, "%d\n", buf);
}
static CLASS_ATTR_RO(fg2_ibatt);

static ssize_t fg2_r1_discharge_flag_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 191, "%u\n", buf);
}
static CLASS_ATTR_RO(fg2_r1_discharge_flag);

static ssize_t fg2_r2_discharge_flag_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 192, "%u\n", buf);
}
static CLASS_ATTR_RO(fg2_r2_discharge_flag);

static ssize_t fg2_record_delta_r1_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 189, "%u\n", buf);
}
static CLASS_ATTR_RO(fg2_record_delta_r1);

static ssize_t fg2_record_delta_r2_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 190, "%u\n", buf);
}
static CLASS_ATTR_RO(fg2_record_delta_r2);

static ssize_t fg2_rm_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 166, "%d\n", buf);
}
static CLASS_ATTR_RO(fg2_rm);

static ssize_t fg2_rsoc_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 171, "%d\n", buf);
}
static CLASS_ATTR_RO(fg2_rsoc);

static ssize_t fg2_soc_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 184, "%u\n", buf);
}
static CLASS_ATTR_RO(fg2_soc);

static ssize_t fg2_soh_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 168, "%d\n", buf);
}
static CLASS_ATTR_RO(fg2_soh);

static ssize_t fg2_temp_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 175, "%d\n", buf);
}
static CLASS_ATTR_RO(fg2_temp);

static ssize_t fg2_tfullq_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 180, "%d\n", buf);
}
static CLASS_ATTR_RO(fg2_tfullq);

static ssize_t fg2_tremq_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 179, "%d\n", buf);
}
static CLASS_ATTR_RO(fg2_tremq);

static ssize_t fg2_vol_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 177, "%u\n", buf);
}
static CLASS_ATTR_RO(fg2_vol);

static ssize_t fg2_vol_max_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 170, "%d\n", buf);
}
static CLASS_ATTR_RO(fg2_vol_max);

static ssize_t fg_raw_soc_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 54, "%u\n", buf);
}
static CLASS_ATTR_RO(fg_raw_soc);

static ssize_t last_node_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 232, "%u\n", buf);
}
static CLASS_ATTR_RO(last_node);

static ssize_t max_life_temp_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 162, "%d\n", buf);
}
static CLASS_ATTR_RO(max_life_temp);

static ssize_t max_life_vol_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 161, "%d\n", buf);
}
static CLASS_ATTR_RO(max_life_vol);

static ssize_t ntc_alarm_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 9, "%u", buf);
}
static ssize_t ntc_alarm_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    int value;
    if (kstrtoint(buf, 0, &value))
        return -EINVAL;
    return sheng_charging_store(bcdev, 9, value, count);
}
static CLASS_ATTR_RW(ntc_alarm);

static ssize_t over_vol_duration_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 163, "%d\n", buf);
}
static CLASS_ATTR_RO(over_vol_duration);

static ssize_t plate_shock_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 107, "%d\n", buf);
}
static ssize_t plate_shock_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    int value;
    if (kstrtoint(buf, 0, &value))
        return -EINVAL;
    return sheng_charging_store(bcdev, 107, value, count);
}
static CLASS_ATTR_RW(plate_shock);

static ssize_t pogo_connect_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 223, "%d\n", buf);
}
static CLASS_ATTR_RO(pogo_connect);

static ssize_t pps_ptf_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 231, "%u\n", buf);
}
static ssize_t pps_ptf_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    int value;
    if (kstrtoint(buf, 0, &value))
        return -EINVAL;
    return sheng_charging_store(bcdev, 231, value, count);
}
static CLASS_ATTR_RW(pps_ptf);

static ssize_t rx_offset_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 81, "%u", buf);
}
static ssize_t rx_offset_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    int value;
    if (kstrtoint(buf, 0, &value))
        return -EINVAL;
    return sheng_charging_store(bcdev, 81, value, count);
}
static CLASS_ATTR_RW(rx_offset);

static ssize_t rx_ss_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 80, "%u", buf);
}
static CLASS_ATTR_RO(rx_ss);

static ssize_t slave_chip_ok_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 164, "%u\n", buf);
}
static CLASS_ATTR_RO(slave_chip_ok);

static ssize_t smart_chg_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 112, "%u\n", buf);
}
static ssize_t smart_chg_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    int value;
    if (kstrtoint(buf, 0, &value))
        return -EINVAL;
    return sheng_charging_store(bcdev, 112, value, count);
}
static CLASS_ATTR_RW(smart_chg);

static ssize_t tx_q_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    return sheng_charging_show(bcdev, 82, "%u", buf);
}
static CLASS_ATTR_RO(tx_q);

static ssize_t wireless_chip_fw_show(const struct class *c,
		const struct class_attribute *attr, char *buf)
{
	struct battery_chg_dev *bcdev =
		container_of(c, struct battery_chg_dev, battery_class);
	struct psy_state *pst = &bcdev->psy_list[PSY_TYPE_XM];
	struct wireless_chip_fw_msg req_msg = { { 0 } };
	int rc;

	req_msg.property_id = XM_PROP_FW_VER;
	req_msg.hdr.owner = MSG_OWNER_BC;
	req_msg.hdr.type = MSG_TYPE_REQ_RESP;
	req_msg.hdr.opcode = pst->opcode_get;

	rc = battery_chg_write(bcdev, &req_msg, sizeof(req_msg));
	if (rc < 0)
		return -EINVAL;

	return scnprintf(buf, PAGE_SIZE, "%.*s\n", WIRELESS_CHIP_FW_VERSION_LEN,
			 bcdev->wireless_chip_fw_version);
}/* SPDX-License-Identifier: GPL-2.0-only */
static ssize_t batt_sn_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    struct sheng_battery_serial_msg request = { .property_id = 160 };
    int rc;
    if (!sheng_charging_live(bcdev))
        return -ENOTCONN;
    request.hdr.owner = MSG_OWNER_BC;
    request.hdr.type = MSG_TYPE_REQ_RESP;
    request.hdr.opcode = bcdev->psy_list[PSY_TYPE_XM].opcode_get;
    rc = battery_chg_write(bcdev, &request, sizeof(request));
    if (rc < 0)
        return rc;
    if (!sheng_charging_live(bcdev))
        return -ENOTCONN;
    return scnprintf(buf, PAGE_SIZE, "%.*s\n", 48, bcdev->sheng_battery_serial);
}
static CLASS_ATTR_RO(batt_sn);

static ssize_t wireless_tx_uuid_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    struct sheng_wireless_uuid_msg request = { .property_id = 73 };
    int rc;
    if (!sheng_charging_live(bcdev))
        return -ENOTCONN;
    request.hdr.owner = MSG_OWNER_BC;
    request.hdr.type = MSG_TYPE_REQ_RESP;
    request.hdr.opcode = bcdev->psy_list[PSY_TYPE_XM].opcode_get;
    rc = battery_chg_write(bcdev, &request, sizeof(request));
    if (rc < 0)
        return rc;
    if (!sheng_charging_live(bcdev))
        return -ENOTCONN;
    return scnprintf(buf, PAGE_SIZE, "%.*s\n", 24, bcdev->sheng_wireless_uuid);
}
static CLASS_ATTR_RO(wireless_tx_uuid);

static ssize_t battery_param_reset_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    int rc;
    if (!sheng_charging_live(bcdev))
        return -ENOTCONN;
    rc = read_property_id(bcdev, &bcdev->psy_list[PSY_TYPE_XM], 113);
    if (rc < 0)
        return rc;
    if (!sheng_charging_live(bcdev))
        return -ENOTCONN;
    /* Shipping factory ABI returns 100 after an acknowledged read, not a progress counter. */
    return scnprintf(buf, PAGE_SIZE, "%u\n", 100);
}
static ssize_t battery_param_reset_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    unsigned int value;
    if (kstrtouint(buf, 0, &value))
        return -EINVAL;
    return sheng_charging_store(bcdev, 113, value, count);
}
static CLASS_ATTR_RW(battery_param_reset);

static ssize_t car_app_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    /* Shipping pogo_flag is initialized by qti_get_DCIN_STATE (property 223).
     * Read the live property rather than introduce a second stale notification cache. */
    return sheng_charging_show(bcdev, 223, "%u", buf);
}
static CLASS_ATTR_RO(car_app);

static ssize_t wireless_version_forcit_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    unsigned long deadline = jiffies + msecs_to_jiffies(5000);
    char *value;
    ssize_t rc;
    if (!sheng_charging_live(bcdev))
        return -ENOTCONN;
    value = kzalloc(PAGE_SIZE, GFP_KERNEL);
    if (!value)
        return -ENOMEM;
    for (;;) {
        rc = wireless_chip_fw_show(c, attr, value);
        if (rc < 0)
            goto out;
        if (!sheng_charging_live(bcdev)) {
            rc = -ENOTCONN;
            goto out;
        }
        if (rc == 0 || value[0] == '\0' || value[0] == '\n') {
            rc = -ENODATA;
            goto out;
        }
        if (strncmp(value, "updating", 8))
            break;
        if (time_after_eq(jiffies, deadline)) {
            rc = -ETIMEDOUT;
            goto out;
        }
        msleep(200);
    }
    rc = scnprintf(buf, PAGE_SIZE, "%s\n",
        !strncmp(value, "00.00.00.00", 11) || strstr(value, "fe") ? "fail" : "pass");
out:
    kfree(value);
    return rc;
}
static CLASS_ATTR_RO(wireless_version_forcit);

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
