
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

/* Shipping sheng bypass control: property 219, independent of input suspend. */
static ssize_t charging_suspend_battery_show(const struct class *c,
        const struct class_attribute *attr, char *buf)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev,
                                               battery_class);
    struct psy_state *pst = &bcdev->psy_list[PSY_TYPE_XM];
    int rc;

    if (atomic_read(&bcdev->state) != PMIC_GLINK_STATE_UP ||
        (bcdev->debug_battery_detected && bcdev->block_tx))
        return -ENOTCONN;
    rc = read_property_id(bcdev, pst, XM_PROP_CHARGING_SUSPEND_BATTERY);
    if (rc < 0)
        return rc;
    if (atomic_read(&bcdev->state) != PMIC_GLINK_STATE_UP)
        return -ENOTCONN;
    return scnprintf(buf, PAGE_SIZE, "%u\n",
        READ_ONCE(pst->prop[XM_PROP_CHARGING_SUSPEND_BATTERY]));
}

static ssize_t charging_suspend_battery_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev,
                                               battery_class);
    bool value;
    int rc;

    if (kstrtobool(buf, &value))
        return -EINVAL;
    if (atomic_read(&bcdev->state) != PMIC_GLINK_STATE_UP ||
        (bcdev->debug_battery_detected && bcdev->block_tx))
        return -ENOTCONN;
    rc = write_property_id(bcdev, &bcdev->psy_list[PSY_TYPE_XM],
                          XM_PROP_CHARGING_SUSPEND_BATTERY, value);
    if (rc < 0)
        return rc;
    if (atomic_read(&bcdev->state) != PMIC_GLINK_STATE_UP)
        return -ENOTCONN;
    return count;
}
static CLASS_ATTR_RW(charging_suspend_battery);

int main(void) { struct battery_chg_dev b={.state=1}; char out[4096],expected[4096]; int before;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[106]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(afp_temp_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==106);
    remote_rc=-ETIMEDOUT;assert(afp_temp_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(afp_temp_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(afp_temp_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(afp_temp_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[114]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(battmoni_isc_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==114);
    remote_rc=-ETIMEDOUT;assert(battmoni_isc_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(battmoni_isc_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(battmoni_isc_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(battmoni_isc_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
remote_rc=0;assert(battmoni_isc_store(&b.battery_class,NULL,"1",1)==1 && last_id==114 && last_value==1);
        assert(battmoni_isc_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert(battmoni_isc_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert(battmoni_isc_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert(battmoni_isc_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert(battmoni_isc_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
before=attempts;assert(battmoni_isc_store(&b.battery_class,NULL,"4294967296",10)==-EINVAL && before==attempts);
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[115]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(battmoni_soa_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==115);
    remote_rc=-ETIMEDOUT;assert(battmoni_soa_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(battmoni_soa_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(battmoni_soa_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(battmoni_soa_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[45]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(blank_status_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==45);
    remote_rc=-ETIMEDOUT;assert(blank_status_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(blank_status_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(blank_status_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(blank_status_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
remote_rc=0;assert(blank_status_store(&b.battery_class,NULL,"1",1)==1 && last_id==45 && last_value==1);
        assert(blank_status_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert(blank_status_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert(blank_status_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert(blank_status_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert(blank_status_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[108]=17;
    snprintf(expected,sizeof(expected),"%u",17);
    assert(cc_short_vbus_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==108);
    remote_rc=-ETIMEDOUT;assert(cc_short_vbus_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(cc_short_vbus_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(cc_short_vbus_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(cc_short_vbus_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
remote_rc=0;assert(cc_short_vbus_store(&b.battery_class,NULL,"1",1)==1 && last_id==108 && last_value==1);
        assert(cc_short_vbus_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert(cc_short_vbus_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert(cc_short_vbus_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert(cc_short_vbus_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert(cc_short_vbus_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
before=attempts;assert(cc_short_vbus_store(&b.battery_class,NULL,"4294967296",10)==-EINVAL && before==attempts);
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[10]=17;
    snprintf(expected,sizeof(expected),"%u",17);
    assert(charger_user_value_map_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==10);
    remote_rc=-ETIMEDOUT;assert(charger_user_value_map_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(charger_user_value_map_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(charger_user_value_map_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(charger_user_value_map_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
remote_rc=0;assert(charger_user_value_map_store(&b.battery_class,NULL,"1",1)==1 && last_id==10 && last_value==1);
        assert(charger_user_value_map_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert(charger_user_value_map_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert(charger_user_value_map_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert(charger_user_value_map_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert(charger_user_value_map_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
before=attempts;assert(charger_user_value_map_store(&b.battery_class,NULL,"4294967296",10)==-EINVAL && before==attempts);
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[110]=17;
    snprintf(expected,sizeof(expected),"%u",17);
    assert(cid_status_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==110);
    remote_rc=-ETIMEDOUT;assert(cid_status_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(cid_status_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(cid_status_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(cid_status_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[11]=17;
    snprintf(expected,sizeof(expected),"%u",17);
    assert(cloud_control_cid_mode_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==11);
    remote_rc=-ETIMEDOUT;assert(cloud_control_cid_mode_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(cloud_control_cid_mode_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(cloud_control_cid_mode_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(cloud_control_cid_mode_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
remote_rc=0;assert(cloud_control_cid_mode_store(&b.battery_class,NULL,"1",1)==1 && last_id==11 && last_value==1);
        assert(cloud_control_cid_mode_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert(cloud_control_cid_mode_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert(cloud_control_cid_mode_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert(cloud_control_cid_mode_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert(cloud_control_cid_mode_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
before=attempts;assert(cloud_control_cid_mode_store(&b.battery_class,NULL,"4294967296",10)==-EINVAL && before==attempts);
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[221]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(cp_ovp_mode_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==221);
    remote_rc=-ETIMEDOUT;assert(cp_ovp_mode_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(cp_ovp_mode_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(cp_ovp_mode_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(cp_ovp_mode_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
remote_rc=0;assert(cp_ovp_mode_store(&b.battery_class,NULL,"1",1)==1 && last_id==221 && last_value==1);
        assert(cp_ovp_mode_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert(cp_ovp_mode_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert(cp_ovp_mode_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert(cp_ovp_mode_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert(cp_ovp_mode_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[218]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(dam_ovpgate_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==218);
    remote_rc=-ETIMEDOUT;assert(dam_ovpgate_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(dam_ovpgate_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(dam_ovpgate_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(dam_ovpgate_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
remote_rc=0;assert(dam_ovpgate_store(&b.battery_class,NULL,"1",1)==1 && last_id==218 && last_value==1);
        assert(dam_ovpgate_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert(dam_ovpgate_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert(dam_ovpgate_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert(dam_ovpgate_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert(dam_ovpgate_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[181]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg1_FullChargeFlag_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==181);
    remote_rc=-ETIMEDOUT;assert(fg1_FullChargeFlag_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg1_FullChargeFlag_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg1_FullChargeFlag_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg1_FullChargeFlag_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[172]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg1_ibatt_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==172);
    remote_rc=-ETIMEDOUT;assert(fg1_ibatt_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg1_ibatt_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg1_ibatt_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg1_ibatt_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[187]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(fg1_r1_discharge_flag_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==187);
    remote_rc=-ETIMEDOUT;assert(fg1_r1_discharge_flag_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg1_r1_discharge_flag_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg1_r1_discharge_flag_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg1_r1_discharge_flag_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[188]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(fg1_r2_discharge_flag_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==188);
    remote_rc=-ETIMEDOUT;assert(fg1_r2_discharge_flag_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg1_r2_discharge_flag_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg1_r2_discharge_flag_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg1_r2_discharge_flag_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[185]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(fg1_record_delta_r1_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==185);
    remote_rc=-ETIMEDOUT;assert(fg1_record_delta_r1_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg1_record_delta_r1_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg1_record_delta_r1_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg1_record_delta_r1_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[186]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(fg1_record_delta_r2_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==186);
    remote_rc=-ETIMEDOUT;assert(fg1_record_delta_r2_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg1_record_delta_r2_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg1_record_delta_r2_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg1_record_delta_r2_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[183]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(fg1_soc_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==183);
    remote_rc=-ETIMEDOUT;assert(fg1_soc_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg1_soc_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg1_soc_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg1_soc_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[174]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg1_temp_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==174);
    remote_rc=-ETIMEDOUT;assert(fg1_temp_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg1_temp_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg1_temp_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg1_temp_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[176]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(fg1_vol_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==176);
    remote_rc=-ETIMEDOUT;assert(fg1_vol_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg1_vol_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg1_vol_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg1_vol_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[182]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg2_FullChargeFlag_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==182);
    remote_rc=-ETIMEDOUT;assert(fg2_FullChargeFlag_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_FullChargeFlag_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_FullChargeFlag_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_FullChargeFlag_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[178]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg2_ai_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==178);
    remote_rc=-ETIMEDOUT;assert(fg2_ai_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_ai_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_ai_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_ai_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[169]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg2_current_max_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==169);
    remote_rc=-ETIMEDOUT;assert(fg2_current_max_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_current_max_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_current_max_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_current_max_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[167]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg2_fcc_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==167);
    remote_rc=-ETIMEDOUT;assert(fg2_fcc_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_fcc_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_fcc_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_fcc_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[173]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg2_ibatt_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==173);
    remote_rc=-ETIMEDOUT;assert(fg2_ibatt_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_ibatt_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_ibatt_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_ibatt_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[191]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(fg2_r1_discharge_flag_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==191);
    remote_rc=-ETIMEDOUT;assert(fg2_r1_discharge_flag_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_r1_discharge_flag_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_r1_discharge_flag_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_r1_discharge_flag_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[192]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(fg2_r2_discharge_flag_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==192);
    remote_rc=-ETIMEDOUT;assert(fg2_r2_discharge_flag_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_r2_discharge_flag_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_r2_discharge_flag_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_r2_discharge_flag_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[189]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(fg2_record_delta_r1_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==189);
    remote_rc=-ETIMEDOUT;assert(fg2_record_delta_r1_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_record_delta_r1_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_record_delta_r1_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_record_delta_r1_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[190]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(fg2_record_delta_r2_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==190);
    remote_rc=-ETIMEDOUT;assert(fg2_record_delta_r2_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_record_delta_r2_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_record_delta_r2_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_record_delta_r2_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[166]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg2_rm_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==166);
    remote_rc=-ETIMEDOUT;assert(fg2_rm_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_rm_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_rm_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_rm_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[171]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg2_rsoc_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==171);
    remote_rc=-ETIMEDOUT;assert(fg2_rsoc_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_rsoc_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_rsoc_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_rsoc_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[184]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(fg2_soc_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==184);
    remote_rc=-ETIMEDOUT;assert(fg2_soc_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_soc_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_soc_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_soc_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[168]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg2_soh_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==168);
    remote_rc=-ETIMEDOUT;assert(fg2_soh_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_soh_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_soh_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_soh_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[175]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg2_temp_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==175);
    remote_rc=-ETIMEDOUT;assert(fg2_temp_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_temp_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_temp_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_temp_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[180]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg2_tfullq_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==180);
    remote_rc=-ETIMEDOUT;assert(fg2_tfullq_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_tfullq_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_tfullq_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_tfullq_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[179]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg2_tremq_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==179);
    remote_rc=-ETIMEDOUT;assert(fg2_tremq_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_tremq_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_tremq_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_tremq_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[177]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(fg2_vol_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==177);
    remote_rc=-ETIMEDOUT;assert(fg2_vol_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_vol_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_vol_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_vol_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[170]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(fg2_vol_max_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==170);
    remote_rc=-ETIMEDOUT;assert(fg2_vol_max_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg2_vol_max_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg2_vol_max_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg2_vol_max_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[54]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(fg_raw_soc_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==54);
    remote_rc=-ETIMEDOUT;assert(fg_raw_soc_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(fg_raw_soc_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(fg_raw_soc_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(fg_raw_soc_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[232]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(last_node_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==232);
    remote_rc=-ETIMEDOUT;assert(last_node_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(last_node_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(last_node_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(last_node_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[162]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(max_life_temp_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==162);
    remote_rc=-ETIMEDOUT;assert(max_life_temp_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(max_life_temp_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(max_life_temp_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(max_life_temp_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[161]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(max_life_vol_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==161);
    remote_rc=-ETIMEDOUT;assert(max_life_vol_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(max_life_vol_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(max_life_vol_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(max_life_vol_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[9]=17;
    snprintf(expected,sizeof(expected),"%u",17);
    assert(ntc_alarm_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==9);
    remote_rc=-ETIMEDOUT;assert(ntc_alarm_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(ntc_alarm_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(ntc_alarm_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(ntc_alarm_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
remote_rc=0;assert(ntc_alarm_store(&b.battery_class,NULL,"1",1)==1 && last_id==9 && last_value==1);
        assert(ntc_alarm_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert(ntc_alarm_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert(ntc_alarm_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert(ntc_alarm_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert(ntc_alarm_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
before=attempts;assert(ntc_alarm_store(&b.battery_class,NULL,"4294967296",10)==-EINVAL && before==attempts);
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[163]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(over_vol_duration_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==163);
    remote_rc=-ETIMEDOUT;assert(over_vol_duration_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(over_vol_duration_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(over_vol_duration_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(over_vol_duration_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[107]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(plate_shock_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==107);
    remote_rc=-ETIMEDOUT;assert(plate_shock_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(plate_shock_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(plate_shock_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(plate_shock_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
remote_rc=0;assert(plate_shock_store(&b.battery_class,NULL,"1",1)==1 && last_id==107 && last_value==1);
        assert(plate_shock_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert(plate_shock_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert(plate_shock_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert(plate_shock_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert(plate_shock_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
before=attempts;assert(plate_shock_store(&b.battery_class,NULL,"4294967296",10)==-EINVAL && before==attempts);
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[223]=17;
    snprintf(expected,sizeof(expected),"%d\n",17);
    assert(pogo_connect_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==223);
    remote_rc=-ETIMEDOUT;assert(pogo_connect_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(pogo_connect_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(pogo_connect_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(pogo_connect_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[231]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(pps_ptf_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==231);
    remote_rc=-ETIMEDOUT;assert(pps_ptf_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(pps_ptf_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(pps_ptf_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(pps_ptf_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
remote_rc=0;assert(pps_ptf_store(&b.battery_class,NULL,"1",1)==1 && last_id==231 && last_value==1);
        assert(pps_ptf_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert(pps_ptf_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert(pps_ptf_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert(pps_ptf_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert(pps_ptf_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
before=attempts;assert(pps_ptf_store(&b.battery_class,NULL,"4294967296",10)==-EINVAL && before==attempts);
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[81]=17;
    snprintf(expected,sizeof(expected),"%u",17);
    assert(rx_offset_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==81);
    remote_rc=-ETIMEDOUT;assert(rx_offset_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(rx_offset_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(rx_offset_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(rx_offset_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
remote_rc=0;assert(rx_offset_store(&b.battery_class,NULL,"1",1)==1 && last_id==81 && last_value==1);
        assert(rx_offset_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert(rx_offset_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert(rx_offset_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert(rx_offset_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert(rx_offset_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
before=attempts;assert(rx_offset_store(&b.battery_class,NULL,"4294967296",10)==-EINVAL && before==attempts);
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[80]=17;
    snprintf(expected,sizeof(expected),"%u",17);
    assert(rx_ss_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==80);
    remote_rc=-ETIMEDOUT;assert(rx_ss_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(rx_ss_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(rx_ss_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(rx_ss_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[164]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(slave_chip_ok_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==164);
    remote_rc=-ETIMEDOUT;assert(slave_chip_ok_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(slave_chip_ok_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(slave_chip_ok_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(slave_chip_ok_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[112]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(smart_chg_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==112);
    remote_rc=-ETIMEDOUT;assert(smart_chg_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(smart_chg_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(smart_chg_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(smart_chg_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
remote_rc=0;assert(smart_chg_store(&b.battery_class,NULL,"1",1)==1 && last_id==112 && last_value==1);
        assert(smart_chg_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert(smart_chg_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert(smart_chg_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert(smart_chg_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert(smart_chg_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
before=attempts;assert(smart_chg_store(&b.battery_class,NULL,"4294967296",10)==-EINVAL && before==attempts);
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[82]=17;
    snprintf(expected,sizeof(expected),"%u",17);
    assert(tx_q_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==82);
    remote_rc=-ETIMEDOUT;assert(tx_q_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(tx_q_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(tx_q_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(tx_q_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
b.state=1;remote_rc=0;drop_after=0;b.psy_list[0].prop[219]=17;
    snprintf(expected,sizeof(expected),"%u\n",17);
    assert(charging_suspend_battery_show(&b.battery_class,NULL,out)==(ssize_t)strlen(expected));
    assert(!strcmp(out,expected) && last_id==219);
    remote_rc=-ETIMEDOUT;assert(charging_suspend_battery_show(&b.battery_class,NULL,out)==-ETIMEDOUT);
    remote_rc=0;b.state=0;before=attempts;assert(charging_suspend_battery_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.state=1;b.debug_battery_detected=true;b.block_tx=true;
    before=attempts;assert(charging_suspend_battery_show(&b.battery_class,NULL,out)==-ENOTCONN && before==attempts);
    b.debug_battery_detected=false;b.block_tx=false;drop_after=1;
    assert(charging_suspend_battery_show(&b.battery_class,NULL,out)==-ENOTCONN);drop_after=0;b.state=1;
remote_rc=0;assert(charging_suspend_battery_store(&b.battery_class,NULL,"1",1)==1 && last_id==219 && last_value==1);
        assert(charging_suspend_battery_store(&b.battery_class,NULL,"0",1)==1 && last_value==0);
        before=attempts;assert(charging_suspend_battery_store(&b.battery_class,NULL,"bad",3)==-EINVAL && before==attempts);
        remote_rc=-EIO;assert(charging_suspend_battery_store(&b.battery_class,NULL,"1",1)==-EIO);
        remote_rc=0;b.state=0;before=attempts;assert(charging_suspend_battery_store(&b.battery_class,NULL,"1",1)==-ENOTCONN && before==attempts);
        b.state=1;drop_after=1;assert(charging_suspend_battery_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);drop_after=0;b.state=1;
puts("Production callbacks: read/write IDs, formats, invalid input, overflow and glink error paths passed");return 0;}
