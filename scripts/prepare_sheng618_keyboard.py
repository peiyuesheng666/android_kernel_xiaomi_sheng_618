#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Adapt the fixed sheng WN8030 reference to stock DT and nanodev0 HAL ABI."""
import difflib
import hashlib
import json
import shutil
from audit_kernel618_modules import ElfModule
from build_sheng618_upstream import ROOT, PROJECT, K618

revision = 'f273227fab85e2ad8391c61c21b3556bd017a726'
reference = ROOT/'diagnostic/keyboard-audit/hid-nanosic-wn8030.c'
assert hashlib.sha256(reference.read_bytes()).hexdigest() == 'e6ee04ddf3a8b8c70337913dd0b3ed5829c6d38659ea5fd363b997052615c3c3'
original = reference.read_text()
text = original


def once(old, new):
    global text
    assert text.count(old) == 1, old[:100]
    text = text.replace(old, new, 1)


def function(name, new):
    global text
    start = text.rfind('\nstatic ', 0, text.index(name+'(')) + 1
    end = text.index('\n}\n', start) + 3
    text = text[:start] + new + '\n' + text[end:]


once('#include <linux/delay.h>', '''#include <linux/gpio.h>
#include <linux/gpio/consumer.h>
#include <linux/of_gpio.h>
#include <linux/kref.h>
#include <linux/poll.h>
#include <linux/regulator/consumer.h>
#include <linux/uaccess.h>
#include <linux/delay.h>''')
once('"vddio",\t/* I/O power supply (1.8V) */\n\t"dvdd",\t\t/* Digital power supply (3.3V) */',
     '"vdd",\t\t/* Stock sheng phandle: L13B. */\n\t"dvdd",\t\t/* Stock sheng phandle: L6B. */\n\t"dvdd-another",\t/* Stock sheng phandle: L12B. */')
a = text.index('\t/* Authentication */')
b = text.index('\n};', a)
text = text[:a]+'''\t/* Stock HAL owns authentication; kernel only transports real messages. */
\tstruct miscdevice raw_misc;
\tstruct kref refs;
\tstruct mutex clients_lock;
\tstruct list_head clients;
\tstruct mutex io_lock;
\tstruct delayed_work fw_worker;
\tunsigned int fw_attempts;
\tbool ready, removing;
'''+text[b:]
once('static const struct regmap_config', '#include "sheng_nanosic_bridge.h"\n\nstatic const struct regmap_config')
# Stock report 0x06 carries media/brightness keys. The sheng reference only
# declares the ordinary 0x05 keyboard collection, so retain the actual stock
# consumer descriptor alongside it, rather than guessing Linux key codes.
stock_module = ElfModule(ROOT.parent/'sheng-lineage/firmware-dump/hardware/modules/vendor_dlkm/nanosic_driver.ko')
assert stock_module.digest == '3e6a7409b9bf87a1f7a8c10f3b5e42d4d9ec862ba7f3b9c3c0d9a614bf0081b4'
section = stock_module.named['.data']
consumer = stock_module.data[section[4]+0xb1a:section[4]+0xb1a+25]
assert consumer.hex() == '050c0901a1018506150026800319002a8003751095018100c0'
a = text.index('static u8 hid_keyboard_descriptor[] = {')
b = text.index('\n};', a)
text = text[:b]+'\n\t/* Stock HID_ConsumerReportDescriptor, report ID 0x06. */\n\t'+', '.join('0x%02x'%v for v in consumer)+',\n'+text[b:]
# The mainline authentication daemon ABI is deliberately not transplanted.
for name in ['nanosic_wn8030_xm_auth_init', 'nanosic_wn8030_xm_auth_s3t1', 'nanosic_wn8030_xm_auth_s5t1']:
    function(name, '')
a = text.index('struct nanosic_auth_req {')
b = text.index('static int nanosic_wn8030_probe(', a)
text = text[:a]+text[b:]
once('if (buf[0] == 0x5)\n\t\tnanosic_wn8030_set_caps_led(nanosic, buf[1]);',
'''if (buf[0] == 0x5) {
\t\tint ret;
\t\tif (count < 2)
\t\t\treturn -EINVAL;
\t\tmutex_lock(&nanosic->io_lock);
\t\tret = nanosic->removing ? -ENODEV : !nanosic->ready ? -EAGAIN :
\t\t\tnanosic_wn8030_set_caps_led(nanosic, buf[1]);
\t\tmutex_unlock(&nanosic->io_lock);
\t\tif (ret)
\t\t\treturn ret;
\t}''')
once('\t\t\tcancel_delayed_work_sync(&nanosic->wake_worker);', '\t\t\tcancel_delayed_work(&nanosic->wake_worker);')
a = text.index('\t/* WN8012(KB) -> HOST, kb auth */')
b = text.index('\n}\n', a)
text = text[:a]+'''\t/* Vendor reports, including auth challenges/replies, go to stock HAL. */
'''+text[b:]
function('nanosic_wn8030_handler', '''static irqreturn_t nanosic_wn8030_handler(int irq, void *data)
{
\tstruct nanosic_wn8030 *nano = data;
\tu8 buf[XM_WN8030_I2C_READ], *p;
\tsize_t left, len;
\tint ret;

\tmutex_lock(&nano->io_lock);
\tif (!nano->ready || nano->removing) {
\t\tmutex_unlock(&nano->io_lock);
\t\treturn IRQ_HANDLED;
\t}
\tif (nano->suspended) {
\t\tnano->suspended = false;
\t\tmutex_unlock(&nano->io_lock);
\t\treturn IRQ_HANDLED;
\t}
\tret = regmap_bulk_read(nano->regmap, 0x4c, buf, sizeof(buf));
\tmutex_unlock(&nano->io_lock);
\tif (ret) {
\t\tdev_warn_ratelimited(nano->dev, "MCU read failed: %d\\n", ret);
\t\treturn IRQ_HANDLED;
\t}
\tif ((buf[0] & 0x7f) != 0x57 ||
\t    (buf[2] != 0x39 && buf[2] != 0x4a && buf[2] != 0x5b && buf[2] != 0x6c))
\t\treturn IRQ_HANDLED;
\tp = buf + 3;
\tleft = sizeof(buf) - 3;
\twhile (left) {
\t\tswitch (*p) {
\t\tcase 0x02: len = 8; break;
\t\tcase 0x05: len = 9; break;
\t\tcase 0x06: len = 5; break;
\t\tcase 0x19: len = 21; break;
\t\tcase 0x22: len = 16; break;
\t\tcase 0x23: len = 32; break;
\t\tcase 0x24: case 0x26: len = left; break;
\t\tdefault: return IRQ_HANDLED;
\t\t}
\t\tif (len > left)
\t\t\treturn IRQ_HANDLED;
\t\tif ((*p == 0x05 || *p == 0x06) && nano->hid_keyboard)
\t\t\thid_input_report(nano->hid_keyboard, HID_INPUT_REPORT, p, len, 0);
\t\telse if (*p == 0x19 && nano->hid_touchpad)
\t\t\thid_input_report(nano->hid_touchpad, HID_INPUT_REPORT, p, len, 0);
\t\telse if (*p >= 0x22) {
\t\t\tsheng_nano_broadcast(nano, p, len);
\t\t\tif (*p == 0x22 || *p == 0x23 || *p == 0x24) {
\t\t\t\tu8 vendor[XM_WN8030_I2C_READ] = {0};
\t\t\t\tmemcpy(vendor + 3, p, len);
\t\t\t\tnanosic_wn8030_handle_vendor(nano, vendor);
\t\t\t}
\t\t}
\t\tp += len;
\t\tleft -= len;
\t}
\treturn IRQ_HANDLED;
}''')
# Validate all host-side firmware lengths before computing checksums or sending.
once('"nanosic/MCU_Upgrade.bin"', '"MCU_Upgrade.bin"')
once('ret = nanosic_wn8030_send_header(nanosic, firmware->data, &ram_code_size);',
'''ram_code_size = get_unaligned_le32(firmware->data + WN8030_HEADER_ADDR +
\t\toffsetof(struct wn8030_bin_header, ram_code_size));
\tif (!ram_code_size || (ram_code_size & 3) ||
\t    ram_code_size > firmware->size - WN8030_CODE_ADDR) {
\t\tret = -EINVAL;
\t\tgoto exit;
\t}
\tret = nanosic_wn8030_send_header(nanosic, firmware->data, &ram_code_size);''')
once('#include <linux/uaccess.h>', '#include <linux/uaccess.h>\n#include <linux/unaligned.h>')
once('data[i] + (data[i+1] << 8) + (data[i+2] << 16) + (data[i+3] << 24)', 'get_unaligned_le32(data + i)')
once('nanosic_wn8030_set_kb_power(nanosic, true);\n\tschedule_delayed_work(&nanosic->wake_worker, msecs_to_jiffies(12000));',
'''mutex_lock(&nanosic->io_lock);
\tif (nanosic->ready && !nanosic->removing && nanosic->keyboard_attached && !nanosic->suspended) {
\t\tnanosic_wn8030_set_kb_power(nanosic, true);
\t\tschedule_delayed_work(&nanosic->wake_worker, msecs_to_jiffies(12000));
\t}
\tmutex_unlock(&nanosic->io_lock);''')
a = text.index('static int nanosic_wn8030_probe(')
text = text[:a]+(PROJECT/'device/xiaomi/sheng/interfaces/kernel/6.18/sheng_nanosic_platform.h').read_text()
stage = K618/'sheng-ports/keyboard'
stage.mkdir(parents=True, exist_ok=True)
(stage/'sheng_nanosic.c').write_text(text)
shutil.copyfile(PROJECT/'device/xiaomi/sheng/interfaces/kernel/6.18/sheng_nanosic_bridge.h', stage/'sheng_nanosic_bridge.h')
(stage/'Kbuild').write_text('# SPDX-License-Identifier: GPL-2.0-only\nobj-m += nanosic_driver.o\nnanosic_driver-y := sheng_nanosic.o\n')
files = {p.name:dict(staged_sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [stage/'sheng_nanosic.c', stage/'sheng_nanosic_bridge.h', stage/'Kbuild']}
patch = ''.join(difflib.unified_diff(original.splitlines(True), text.splitlines(True), fromfile='a/drivers/hid/hid-nanosic-wn8030.c', tofile='b/drivers/hid/hid-nanosic-wn8030.c'))
(PROJECT/'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-nanosic.patch').write_text(patch)
stock = ROOT.parent/'sheng-lineage/firmware-dump'
inputs = [reference, ROOT/'diagnostic/keyboard-audit/sm8550-xiaomi-sheng.dts', ROOT/'diagnostic/disklog-r5/live.dts',
          stock/'hardware/modules/vendor_dlkm/nanosic_driver.ko', stock/'partitions/odm/firmware/MCU_Upgrade.bin',
          stock/'partitions/odm/bin/hw/vendor.xiaomi.hardware.keyboardnanoapp@1.0-service']
report = dict(files=files, reference=dict(repository='https://github.com/map220v/sm8550-mainline', revision=revision,license='GPL-2.0-only'),
    inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
    prior_sources='MiCode sheng only provides charger companion, LOS nuwa has no sheng MCU transport; reference targets sheng explicitly',
    adaptation='Stock GPIO/supply property names, original 66-byte write and stripped vendor-packet read ABI on nanodev0; stock HAL owns authentication',
    binary_evidence='write0x2950 truncates66 and invokes I2C; read0x1ef0 ring72-byte entries and copies data+4; parse0xe314 strips3 bytes, fixed report lengths from switch at rodata0x19580; poll/ioctl return ENOSYS',
    firmware='Existing stock MCU_Upgrade.bin, checked length/header and chip verification; volatile RAM download only, no keyboard upgrade files replaced',
    consumer_descriptor=dict(symbol='HID_ConsumerReportDescriptor', section='.data', offset='0xb1a', length=len(consumer),
        sha256=hashlib.sha256(consumer).hexdigest(), report_id=6),
    hardware_result='pending', limitations='Vendor charger injection, edge filtering and relative mouse report0x02 not yet implemented; physical keyboard acceptance required')
(PROJECT/'reports/kernel618-keyboard-source.json').write_text(json.dumps(report,indent=2)+'\n')
print('Staged stock-HyperOS sheng keyboard transport')
