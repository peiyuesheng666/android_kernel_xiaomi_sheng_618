/* SPDX-License-Identifier: GPL-2.0-only */
/* Shared production policy; native adapter authentication always has priority. */
struct sheng_pps_sample {
    bool online, pps, ready, verified, healthy, authenticated, input_suspended, verifying;
    u32 svid, adapter_id, apdo_watts, power_watts;
};
struct sheng_pps_policy {
    bool connected;
    unsigned int attempts;
};
enum sheng_pps_action {
    SHENG_PPS_OFFLINE, SHENG_PPS_EXISTING, SHENG_PPS_NATIVE,
    SHENG_PPS_BLOCKED, SHENG_PPS_UNLOCK
};

static enum sheng_pps_action sheng_pps_decide(struct sheng_pps_policy *p,
        const struct sheng_pps_sample *s)
{
    if (!s->online) {
        memset(p, 0, sizeof(*p));
        return SHENG_PPS_OFFLINE;
    }
    p->connected = true;
    if (s->verified)
        return SHENG_PPS_EXISTING;
    /* SVID can be retained after unplug. A zero native adapter ID plus current
     * <100 W capability is eligible even when an old Xiaomi SVID remains. */
    if (!s->pps || s->adapter_id || ((!s->svid || s->svid == 0x2717) &&
            (s->apdo_watts >= 100 || s->power_watts >= 100))) {
        return SHENG_PPS_NATIVE;
    }
    if (s->verifying || !s->ready || !s->apdo_watts || !s->power_watts) {
        return SHENG_PPS_BLOCKED;
    }
    if (p->attempts >= 3 || !s->healthy ||
            !s->authenticated || s->input_suspended) {
        return SHENG_PPS_BLOCKED;
    }
    return SHENG_PPS_UNLOCK;
}
