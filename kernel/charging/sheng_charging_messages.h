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
