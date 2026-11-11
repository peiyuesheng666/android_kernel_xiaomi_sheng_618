/* SPDX-License-Identifier: GPL-2.0-only */
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
