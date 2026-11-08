#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage Xiaomi's public NT36532/THP sources with verified sheng parameters."""
import difflib
import hashlib
import json
import subprocess
from build_sheng618_upstream import ROOT, K618, PROJECT

source = ROOT / 'src/micode-touch'
stage = K618 / 'sheng-ports/touch'
revision = subprocess.check_output(['git', '-C', source, 'rev-parse', 'HEAD'], text=True).strip()
assert revision == '6957f6b646d1c919e175e6f9000eb50c8635273c'

def change(text, old, new):
    assert text.count(old) == 1, old[:120]
    return text.replace(old, new, 1)

records, patches = {}, []
for subdir in ('xiaomi', 'p81/nt36532'):
    for path in sorted((source / subdir).iterdir()):
        if path.suffix not in ('.h', '.c'):
            continue
        name = path.relative_to(source).as_posix()
        original = path.read_text()
        text = original
        text = text.replace('.llseek = no_llseek,', '.llseek = NULL,')
        text = text.replace('MODULE_IMPORT_NS(VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver);',
                            'MODULE_IMPORT_NS("VFS_internal_I_am_really_a_filesystem_and_am_NOT_a_driver");')
        if name.endswith('/nt36xxx.h'):
            for old, new in [
                ('#define TOUCH_MAX_WIDTH 2136', '#define TOUCH_MAX_WIDTH 2032'),
                ('#define TOUCH_MAX_HEIGHT 3200', '#define TOUCH_MAX_HEIGHT 3048'),
                ('#define PEN_MAX_WIDTH 2136', '#define PEN_MAX_WIDTH 2032'),
                ('#define PEN_MAX_HEIGHT 3200', '#define PEN_MAX_HEIGHT 3048'),
                ('#define SUPER_RESOLUTION_FACOTR 100', '#define SUPER_RESOLUTION_FACOTR 10'),
            ]:
                text = change(text, old, new)
            text = text.replace('novatek_nt36532_piano_fw_csot.bin', 'novatek_nt36532_n81a_fw_csot.bin')
            text = text.replace('novatek_nt36532_piano_mp_csot.bin', 'novatek_nt36532_n81a_mp_csot.bin')
            text = text.replace('piano_nova_csot_thp_config.ini', 'n81a_nova_thp_config.ini')
            # This stage is gated to the verified CSOT sheng panel; no piano BOE firmware.
            text = text.replace('novatek_nt36532_piano_fw_boe.bin', 'sheng-unsupported-panel.bin')
            text = text.replace('novatek_nt36532_piano_mp_boe.bin', 'sheng-unsupported-panel-mp.bin')
            text = text.replace('piano_nova_boe_thp_config.ini', 'sheng-unsupported-panel.ini')
        if name.endswith('/nt36xxx.c'):
            text = text.replace('->master->flags', '->controller->flags').replace('SPI_MASTER_HALF_DUPLEX', 'SPI_CONTROLLER_HALF_DUPLEX')
            text = change(text, 'extern ssize_t mi_dsi_panel_lockdown_info_read(unsigned char *plockdowninfo);',
                '''/* N81A's bootloader publishes these bytes in SMEM item 500 (MiCode parser). */
#include <linux/soc/qcom/smem.h>
static ssize_t mi_dsi_panel_lockdown_info_read(unsigned char *info)
{
	size_t size;
	const void *data;

	if (!info)
		return -EINVAL;
	data = qcom_smem_get(QCOM_SMEM_HOST_ANY, 500, &size);
	if (IS_ERR(data))
		return PTR_ERR(data);
	if (size < 8)
		return -EINVAL;
	memcpy(info, data, 8);
	return info[0];
}''')
            text = change(text, '\tNVT_LOG("start\\n");\n\n\t/*set spi controller',
                '''	struct device_node *panel;
	u64 panel_id = 0;

	panel = of_parse_phandle(client->dev.of_node, "panel", 0);
	if (panel)
		of_property_read_u64(panel, "mi,panel-id", &panel_id);
	of_node_put(panel);
	if (panel_id != 0x4e38316150360200ULL)
		return -ENODEV;
	NVT_LOG("start sheng N81A\\n");

	/*set spi controller''')
            # sheng has one verified panel; piano's optional LCD-ID GPIO is absent.
            a = text.index('\tts->lcd_id_gpio = of_get_named_gpio(')
            b = text.index('\n\tret = of_property_read_u32', a)
            text = text[:a] + '\t/* sheng N81A CSOT, verified by panel-id above. */\n\tts->lcd_id_value = 0;\n' + text[b:]
            # SPI core may use the immediate transfer path without a worker.
            text = text.replace('if(client->controller) {', 'if (client->controller && client->controller->kworker) {')
        if name == 'xiaomi/xiaomi_touch_core.c':
            text = change(text, '\tnetlink_cfg.cb_mutex = NULL;\n', '')
            text = change(text, 'static int xiaomi_touch_remove(struct platform_device *pdev)',
                          'static void xiaomi_touch_remove(struct platform_device *pdev)')
            a = text.index('static void xiaomi_touch_remove(')
            b = text.index('\n}\n', a)
            text = text[:a] + text[a:b].replace('\n\treturn 0;', '') + text[b:]
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        records[name] = dict(source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                             staged_sha256=hashlib.sha256(text.encode()).hexdigest())
        patches.extend(difflib.unified_diff(original.splitlines(True), text.splitlines(True),
            fromfile='a/' + name, tofile='b/' + name, n=3))

kbuild = '''# SPDX-License-Identifier: GPL-2.0-only
ccflags-y += -include $(src)/../../../tp-autoconf.h
ccflags-y += -I$(src)/../../../soc/include -I$(src)/../../../vendor/qcom/opensource/display-drivers/include
ccflags-y += -DTOUCH_THP_SUPPORT=1 -DTOUCH_IS_TDDI -DTOUCH_STYLUS_SUPPORT -DDISABLE_POWER_STATUS
ccflags-y += -DCONFIG_TOUCHSCREEN_NVT_DEBUG_FS=1
ccflags-y += -Wno-missing-prototypes -Wno-missing-declarations
obj-m += xiaomi_touch.o nt36532_touch.o
xiaomi_touch-y := xiaomi/xiaomi_touch_knock_data.o xiaomi/xiaomi_touch_core.o xiaomi/xiaomi_touch_proc.o xiaomi/xiaomi_touch_operations.o xiaomi/xiaomi_touch_sys.o xiaomi/xiaomi_touch_mode.o xiaomi/xiaomi_touch_evdev.o xiaomi/xiaomi_touch_device.o
nt36532_touch-y := p81/nt36532/nt36xxx.o p81/nt36532/nt36xxx_fw_update.o p81/nt36532/nt36xxx_ext_proc.o p81/nt36532/nt36xxx_mp_ctrlram.o
'''
# Paths relative to sheng-ports/touch are two levels below K618.
kbuild = kbuild.replace('../../../', '../../')
(stage / 'Kbuild').write_text(kbuild)
destination = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18'
(destination / 'touch-nt36532.patch').write_text(''.join(patches))
(destination / 'touch-nt36532.Kbuild').write_text(kbuild)
(PROJECT / 'reports/kernel618-touch-source.json').write_text(json.dumps(dict(
    source_repository='https://github.com/MiCode/vendor_xiaomi_proprietary_touch-driver',
    revision=revision, branch='piano-w-oss', files=records,
    scope='Public NT36532 THP and M80p/P81c implementation adapted to stock sheng ABI',
    parameters_reference='reports/device/kernel618-input-stock-reference',
    lockdown_reference='MiCode sheng display 6461221b SMEM item 500; bounded eight-byte read',
    firmware='Only verified sheng CSOT filenames; no other-device firmware imported',
    runtime_verified=False), indent=2)+'\n')
print('Staged', stage)
