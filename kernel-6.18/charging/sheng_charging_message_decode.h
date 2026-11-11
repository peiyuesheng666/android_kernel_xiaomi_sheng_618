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
