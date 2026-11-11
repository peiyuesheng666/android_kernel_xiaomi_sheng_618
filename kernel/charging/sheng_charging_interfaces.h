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

