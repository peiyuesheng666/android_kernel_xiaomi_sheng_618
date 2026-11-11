/* SPDX-License-Identifier: GPL-2.0-only */
static bool sheng_pps_auto_verify = true;
module_param_named(sheng_pps_auto_verify, sheng_pps_auto_verify, bool, 0600);
MODULE_PARM_DESC(sheng_pps_auto_verify,
        "Maintain eligible third-party PPS after native discovery; N disables automatic writes");

static bool sheng_pps_live(struct battery_chg_dev *bcdev)
{
    return !READ_ONCE(bcdev->sheng_pps_stopping) &&
        atomic_read(&bcdev->state) == PMIC_GLINK_STATE_UP &&
        !(bcdev->debug_battery_detected && bcdev->block_tx);
}

static int sheng_pps_read(struct battery_chg_dev *bcdev, int type, u32 id, u32 *value)
{
    struct psy_state *pst = &bcdev->psy_list[type];
    int rc;
    if (!sheng_pps_live(bcdev))
        return -ENOTCONN;
    rc = read_property_id(bcdev, pst, id);
    if (rc < 0)
        return rc;
    if (!sheng_pps_live(bcdev))
        return -ENOTCONN;
    *value = READ_ONCE(pst->prop[id]);
    return 0;
}

static int sheng_pps_snapshot(struct battery_chg_dev *bcdev, struct sheng_pps_sample *s)
{
    u32 value, main_auth, slave_auth, match;
    int rc;
    memset(s, 0, sizeof(*s));
    rc = sheng_pps_read(bcdev, PSY_TYPE_USB, USB_ONLINE, &value);
    if (rc < 0)
        return rc;
    s->online = value == 1;
    if (!s->online)
        return 0;
    rc = sheng_pps_read(bcdev, PSY_TYPE_USB, USB_REAL_TYPE, &value);
    if (rc < 0)
        return rc;
    s->pps = value == POWER_SUPPLY_USB_TYPE_PD_PPS;
    if (!s->pps)
        return 0;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_PD_VERIFED, &value);
    if (rc < 0)
        return rc;
    s->verified = value == 1;
    if (s->verified)
        return 0;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_CURRENT_STATE, &value);
    if (rc < 0)
        return rc;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_VERIFY_PROCESS, &match);
    if (rc < 0)
        return rc;
    s->verifying = match != 0;
    /* Shipping current_state_show maps firmware state 31 to SNK_Ready. */
    s->ready = value == 31;
#define SHENG_PPS_GET(id, field) do { \
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, id, &s->field); \
    if (rc < 0) return rc; \
} while (0)
    SHENG_PPS_GET(XM_PROP_ADAPTER_SVID, svid);
    SHENG_PPS_GET(XM_PROP_ADAPTER_ID, adapter_id);
    SHENG_PPS_GET(XM_PROP_APDO_MAX, apdo_watts);
    SHENG_PPS_GET(XM_PROP_POWER_MAX, power_watts);
#undef SHENG_PPS_GET
    rc = sheng_pps_read(bcdev, PSY_TYPE_BATTERY, BATT_HEALTH, &value);
    if (rc < 0)
        return rc;
    s->healthy = value == POWER_SUPPLY_HEALTH_GOOD;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_AUTHENTIC, &main_auth);
    if (rc < 0)
        return rc;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_SLAVE_AUTHENTIC, &slave_auth);
    if (rc < 0)
        return rc;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_BATTERY_ADAPT_POWER_MATCH, &match);
    if (rc < 0)
        return rc;
    s->authenticated = main_auth == 1 && slave_auth == 1 && match == 1;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_INPUT_SUSPEND, &value);
    if (rc < 0)
        return rc;
    s->input_suspended = value != 0;
    return 0;
}

static void sheng_pps_auto_work(struct work_struct *work)
{
    struct battery_chg_dev *bcdev = container_of(to_delayed_work(work),
            struct battery_chg_dev, sheng_pps_work);
    struct sheng_pps_sample sample, first;
    enum sheng_pps_action action;
    int epoch;
    u32 verified, online, type;
    bool retry = false, changed = false;
    unsigned long retry_delay = 0;
    int rc;
    if (!READ_ONCE(sheng_pps_auto_verify) || READ_ONCE(bcdev->sheng_pps_stopping))
        return;
    mutex_lock(&bcdev->sheng_pps_lock);
    if (atomic_xchg(&bcdev->sheng_pps_reset, 0))
        memset(&bcdev->sheng_pps, 0, sizeof(bcdev->sheng_pps));
    epoch = atomic_read(&bcdev->sheng_pps_epoch);
    rc = sheng_pps_snapshot(bcdev, &sample);
    if (rc < 0)
        goto error;
    action = sheng_pps_decide(&bcdev->sheng_pps, &sample);
    /* Only attached PPS is monitored; already verified samples cost three reads.
     * Events and stores kick immediately. The five-second fallback catches
     * firmware-only clears; it is not a recognition grace period. */
    retry = sample.online && sample.pps && bcdev->sheng_pps.attempts < 3;
    retry_delay = 5 * HZ;
    if (action != SHENG_PPS_UNLOCK)
        goto out;
    /* Revalidate the complete source and protection state immediately before writing. */
    first = sample;
    rc = sheng_pps_snapshot(bcdev, &sample);
    if (rc < 0)
        goto error;
    action = sheng_pps_decide(&bcdev->sheng_pps, &sample);
    if (action != SHENG_PPS_UNLOCK || !READ_ONCE(sheng_pps_auto_verify) ||
            !sheng_pps_live(bcdev) || epoch != atomic_read(&bcdev->sheng_pps_epoch)) {
        retry = sample.online && sample.pps && bcdev->sheng_pps.attempts < 3;
        retry_delay = 0;
        goto out;
    }
    if (first.svid != sample.svid || first.adapter_id != sample.adapter_id ||
            first.apdo_watts != sample.apdo_watts || first.power_watts != sample.power_watts) {
        retry = true;
        retry_delay = 0;
        goto out;
    }
    rc = write_property_id(bcdev, &bcdev->psy_list[PSY_TYPE_XM], XM_PROP_PD_VERIFED, 1);
    if (rc < 0)
        goto write_error;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_PD_VERIFED, &verified);
    if (rc < 0)
        goto write_error;
    if (verified != 1) {
        rc = -EIO;
        goto write_error;
    }
    rc = sheng_pps_read(bcdev, PSY_TYPE_USB, USB_ONLINE, &online);
    if (rc < 0)
        goto write_error;
    rc = sheng_pps_read(bcdev, PSY_TYPE_USB, USB_REAL_TYPE, &type);
    if (rc < 0)
        goto write_error;
    if (online != 1 || type != POWER_SUPPLY_USB_TYPE_PD_PPS) {
        rc = -ENOTCONN;
        goto write_error;
    }
    dev_info(bcdev->dev, "sheng PPS auto verified: svid=%04x id=%08x APDO=%u W\n",
            sample.svid, sample.adapter_id, sample.apdo_watts);
    bcdev->sheng_pps.attempts = 0;
    changed = true;
    goto out;
error:
write_error:
    if (bcdev->sheng_pps.attempts < 3)
        ++bcdev->sheng_pps.attempts;
    retry_delay = HZ;
    retry = bcdev->sheng_pps.attempts < 3 && sheng_pps_live(bcdev);
    dev_warn(bcdev->dev, "sheng PPS auto verification deferred/failed: %d\n", rc);
out:
    mutex_unlock(&bcdev->sheng_pps_lock);
    if (changed && !READ_ONCE(bcdev->sheng_pps_stopping)) {
        if (bcdev->psy_list[PSY_TYPE_USB].psy)
            power_supply_changed(bcdev->psy_list[PSY_TYPE_USB].psy);
        schedule_delayed_work(&bcdev->xm_prop_change_work, 0);
    }
    if (retry && READ_ONCE(sheng_pps_auto_verify) && !READ_ONCE(bcdev->sheng_pps_stopping))
        mod_delayed_work(system_freezable_wq, &bcdev->sheng_pps_work, retry_delay);
}

static void sheng_pps_kick(struct battery_chg_dev *bcdev)
{
    if (READ_ONCE(sheng_pps_auto_verify) && !READ_ONCE(bcdev->sheng_pps_stopping))
        mod_delayed_work(system_freezable_wq, &bcdev->sheng_pps_work, 0);
}
