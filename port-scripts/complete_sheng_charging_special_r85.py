#!/usr/bin/env python3
"""Restore the remaining shipping charger interfaces with their distinct message ABIs."""
from pathlib import Path
import difflib
import hashlib
import json

workspace=Path(__file__).resolve().parents[1]
project=Path('/root/sheng-618-repair-r85-project');build=Path('/root/sheng-618-repair-r85-build')
receipt_path=project/'provenance/repair-r85.json';receipt=json.loads(receipt_path.read_text())
relative='k618/soc/drivers/power/supply/qti_battery_charger.c';p=build/relative
source=p.read_text();assert hashlib.sha256(source.encode()).hexdigest()==receipt['files'][relative]['after']
messages='''/* SPDX-License-Identifier: GPL-2.0-only */
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
'''
decoder='''/* SPDX-License-Identifier: GPL-2.0-only */
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
        bcdev->sheng_battery_serial[sizeof(serial->serial)] = '\\0';
        return true;
    }
    if (len == sizeof(*uuid) && uuid->property_id == 73) {
        memcpy(bcdev->sheng_wireless_uuid, uuid->version, sizeof(uuid->version));
        bcdev->sheng_wireless_uuid[sizeof(uuid->version)] = '\\0';
        return true;
    }
    return false;
}
'''
special='''/* SPDX-License-Identifier: GPL-2.0-only */
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
    return scnprintf(buf, PAGE_SIZE, "%.*s\\n", 48, bcdev->sheng_battery_serial);
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
    return scnprintf(buf, PAGE_SIZE, "%.*s\\n", 24, bcdev->sheng_wireless_uuid);
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
    return scnprintf(buf, PAGE_SIZE, "%u\\n", 100);
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
        if (strncmp(value, "updating", 8))
            break;
        if (time_after_eq(jiffies, deadline)) {
            rc = -ETIMEDOUT;
            goto out;
        }
        msleep(200);
    }
    rc = scnprintf(buf, PAGE_SIZE, "%s\\n",
        !strncmp(value, "00.00.00.00", 11) || strstr(value, "fe") ? "fail" : "pass");
out:
    kfree(value);
    return rc;
}
static CLASS_ATTR_RO(wireless_version_forcit);
'''
files={
'k618/soc/drivers/power/supply/sheng_charging_messages.h':messages,
'k618/soc/drivers/power/supply/sheng_charging_message_decode.h':decoder,
'k618/soc/drivers/power/supply/sheng_charging_special.h':special}
for name,value in files.items():
    target=build/name;assert not target.exists();target.write_text(value)
    receipt['files'][name]=dict(before=None,after=hashlib.sha256(value.encode()).hexdigest())
anchor='struct battery_model_resp_msg {';assert source.count(anchor)==1
source=source.replace(anchor,'#include "sheng_charging_messages.h"\n\n'+anchor)
anchor='\tstruct mutex sheng_pen_lock;';assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n\tchar sheng_battery_serial[49];\n\tchar sheng_wireless_uuid[25];')
anchor='static bool validate_message(';assert source.count(anchor)==1
source=source.replace(anchor,'#include "sheng_charging_message_decode.h"\n\n'+anchor)
anchor='\tcase BC_XM_STATUS_GET:\n\t\tpst = &bcdev->psy_list[PSY_TYPE_XM];\n';assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n\t\tif (sheng_charging_decode_text(bcdev, data, len)) {\n\t\t\tack_set = true;\n\t\t\tbreak;\n\t\t}\n')
anchor='#include "sheng_charging_interfaces.h"';assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n#include "sheng_charging_special.h"')
anchor='static struct attribute *battery_class_attrs[] = {';assert source.count(anchor)==1
names=receipt['deferred_non_scalar_nodes'];assert len(names)==5
source=source.replace(anchor,anchor+''.join('\n\t&class_attr_'+n+'.attr,' for n in names))
p.write_text(source);receipt['files'][relative]['after']=hashlib.sha256(source.encode()).hexdigest()
receipt['restored_special_nodes']=names;receipt['deferred_non_scalar_nodes']=[]
receipt['special_abi_notes']=dict(serial_request_bytes=64,serial_id=160,serial_payload_bytes=48,
    uuid_request_bytes=44,uuid_id=73,uuid_payload_bytes=24,pogo_source='live DCIN property 223',
    factory_reset_read='shipping constant 100 after live acknowledgement',factory_version_timeout_ms=5000)
patch=''
for name,state in receipt['files'].items():
    if name==relative:before=(Path('/root/sheng-618-pen-release-build')/name).read_text()
    elif state['before'] is None:before=''
    else:raise RuntimeError(name)
    after=(build/name).read_text()
    patch+=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
        fromfile='a/'+name if before else '/dev/null',tofile='b/'+name))
(project/receipt['patch']).write_text(patch);receipt['patch_sha256']=hashlib.sha256(patch.encode()).hexdigest()
receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
(workspace/'reports/kernel618-repair-r85-stage.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(dict(restored_special=names,source_sha256=receipt['files'][relative]['after'],runtime_verified=False)),flush=True)
