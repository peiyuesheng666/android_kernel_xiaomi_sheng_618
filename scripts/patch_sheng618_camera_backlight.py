#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restore sheng camera power ABI and the stock dual KTZ8866 backlight path."""
import difflib
import hashlib
import json
import subprocess
from build_sheng618_upstream import ROOT, K618, PROJECT

backup = ROOT / 'diagnostic/hardware-r25/source-before'
reference = ROOT / 'src/micode-display/msm/mi_disp'
camera_reference = ROOT / 'src/micode-camera/drivers/cam_sensor_module/cam_sensor_utils'
files = {}
receipt_path = PROJECT / 'reports/kernel618-camera-backlight-source.json'
prior = json.loads(receipt_path.read_text())['files'] if receipt_path.exists() else {}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(name):
    saved = backup / name
    if not saved.exists():
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes((K618 / name).read_bytes())
    return saved.read_text()


def once(text, old, new):
    assert text.count(old) == 1, old[:120]
    return text.replace(old, new, 1)


base = 'vendor/qcom/opensource/camera-kernel/drivers/cam_sensor_module/cam_sensor_utils/'
name = base + 'cam_sensor_cmn_header.h'
text = read(name)
text = once(text, '\tSENSOR_CUSTOM_REG3,\n',
    '\t/* HyperOS sheng ABI: MiCode sheng/LOS nuwa BOB=13, BOB2=14. */\n'
    '\tSENSOR_BOB = 13,\n\tSENSOR_BOB2 = 14,\n\tSENSOR_CUSTOM_REG3,\n')
files[name] = text
name = base + 'cam_sensor_util.c'
text = read(name)
official = (camera_reference / 'cam_sensor_util.c').read_text()
a = official.index('\t\tcase SENSOR_BOB:\n')
b = official.index('\t\t/* xiaomi add end*/', a)
bob = official[a:b]
assert '"cam_bob2"' in bob and 'VALIDATE_VOLTAGE' in bob
text = once(text, '\t\tcase SENSOR_CUSTOM_REG3:\n\t\t\tfor (j = 0; j < num_vreg; j++) {',
    bob + '\t\tcase SENSOR_CUSTOM_REG3:\n\t\t\tfor (j = 0; j < num_vreg; j++) {')
assert text.count('\t\tcase SENSOR_CUSTOM_REG3:\n') == 4
text = text.replace('\t\tcase SENSOR_CUSTOM_REG2:\n\t\tcase SENSOR_CUSTOM_REG3:\n',
    '\t\tcase SENSOR_CUSTOM_REG2:\n\t\tcase SENSOR_BOB:\n\t\tcase SENSOR_BOB2:\n\t\tcase SENSOR_CUSTOM_REG3:\n')
assert text.count('\t\tcase SENSOR_BOB2:\n') == 4
files[name] = text

display = 'vendor/qcom/opensource/display-drivers/'
name = display + 'msm/sheng_ktz8866.h'
files[name] = (reference / 'mi_backlight_ktz8866.h').read_text()
files[name] = '#include <linux/types.h>\n#include <linux/list.h>\n' + files[name]
files[name] = once(files[name], 'struct ktz8866_led {', 'struct ktz8866_led {\n\t\tstruct device *dev;')
files[name] += '\nint sheng_ktz8866_init(void);\nvoid sheng_ktz8866_exit(void);\nint ktz8866_backlight_update_status(unsigned int level);\n'
name = display + 'msm/sheng_ktz8866.c'
text = (reference / 'mi_backlight_ktz8866.c').read_text()
text = '#include <linux/ratelimit.h>\n#include <linux/timekeeping.h>\n' + text
text = text.replace('#include "mi_backlight_ktz8866.h"', '#include "sheng_ktz8866.h"')
text = once(text, '#define u8\tunsigned int\nstatic struct list_head ktz8866_dev_list;\nstatic struct mutex ktz8866_dev_list_mutex;',
    'static LIST_HEAD(ktz8866_dev_list);\nstatic DEFINE_MUTEX(ktz8866_dev_list_mutex);')
text = text.replace('u8 *data', 'unsigned int *data')
text = text.replace('u8 reg', 'unsigned int reg')
a = text.index('static int ktz_update_status(')
b = text.index('\nstatic int ktz_get_brightness(', a)
text = text[:a] + '''static int ktz_update_status(struct ktz8866_led *ktz, unsigned int level)
{
	unsigned int scaled, brightness;
	int ret;

	if (level > BL_LEVEL_MAX_HBM)
		return -EINVAL;
	if (level <= BL_LEVEL_MAX)
		scaled = level * NORMAL_MAX_DVB / BL_LEVEL_MAX;
	else
		scaled = (level - 2048) * (2047 - NORMAL_MAX_DVB) / 2047 + NORMAL_MAX_DVB;
	brightness = mi_bl_level_remap[scaled];
	if (brightness == ktz->level)
		return 0;
	/* Keep the sheng register values, remap and bias-preserving enable bits. */
	if (!brightness) {
		ret = ktz8866_write(ktz, KTZ8866_DISP_BL_ENABLE, 0x3f);
		if (ret)
			return ret;
		ktz->ktz8866_status = false;
		usleep_range(10000, 10010);
	}
	ret = ktz8866_write(ktz, KTZ8866_DISP_BB_LSB, brightness & 7);
	if (ret)
		return ret;
	ret = ktz8866_write(ktz, KTZ8866_DISP_BB_MSB, (brightness >> 3) & 0xff);
	if (ret)
		return ret;
	if (brightness && !ktz->ktz8866_status) {
		ret = ktz8866_write(ktz, KTZ8866_DISP_BL_ENABLE, 0x7f);
		if (ret)
			return ret;
		ktz->ktz8866_status = true;
	}
	ktz->level = brightness;
	return 0;
}
''' + text[b:]
a = text.index('int ktz8866_backlight_update_status(')
b = text.index('\nstatic int ktz8866_probe(', a)
text = text[:a] + '''int ktz8866_backlight_update_status(unsigned int level)
{
	struct ktz8866_led *ktz;
	int ret = 0, err;
	static DEFINE_RATELIMIT_STATE(trace_limit, HZ, 4);
	bool trace = ktime_get_boottime_seconds() < 120 && __ratelimit(&trace_limit);

	mutex_lock(&ktz8866_dev_list_mutex);
	if (list_empty(&ktz8866_dev_list))
		ret = -ENODEV;
	list_for_each_entry(ktz, &ktz8866_dev_list, entry) {
		err = ktz->ops->update_status(ktz, level);
		if (err && !ret)
			ret = err;
		if (trace) {
			unsigned int lsb, msb, enable;
			int readback = regmap_read(ktz->regmap, KTZ8866_DISP_BB_LSB, &lsb);
			if (!readback)
				readback = regmap_read(ktz->regmap, KTZ8866_DISP_BB_MSB, &msb);
			if (!readback)
				readback = regmap_read(ktz->regmap, KTZ8866_DISP_BL_ENABLE, &enable);
			if (!readback)
				dev_info(ktz->dev, "sheng_backlight requested=%u cached=%d actual=%u enable=0x%x write_rc=%d\\n",
					level, ktz->level, ((msb & 0xff) << 3) | (lsb & 7), enable, err);
		}
	}
	mutex_unlock(&ktz8866_dev_list_mutex);
	return ret;
}
''' + text[b:]
text = once(text, 'static int ktz8866_probe(struct i2c_client *i2c,\n\t\t\t  const struct i2c_device_id *id)',
    'static int ktz8866_probe(struct i2c_client *i2c)')
telemetry = r'''/* Read actual I2C registers without providing a raw write interface. */
static ssize_t register_brightness_show(struct device *dev,
                                      struct device_attribute *attr, char *buf)
{
	struct ktz8866_led *ktz = dev_get_drvdata(dev);
	unsigned int lsb, msb, enable;
	int ret;

	mutex_lock(&ktz8866_dev_list_mutex);
	ret = regmap_read(ktz->regmap, KTZ8866_DISP_BB_LSB, &lsb);
	if (!ret)
		ret = regmap_read(ktz->regmap, KTZ8866_DISP_BB_MSB, &msb);
	if (!ret)
		ret = regmap_read(ktz->regmap, KTZ8866_DISP_BL_ENABLE, &enable);
	if (!ret)
		ret = sysfs_emit(buf, "cached=%d actual=%u enable=0x%02x\n",
			ktz->level, ((msb & 0xff) << 3) | (lsb & 7), enable);
	mutex_unlock(&ktz8866_dev_list_mutex);
	return ret;
}
static DEVICE_ATTR_RO(register_brightness);
static struct attribute *ktz8866_attrs[] = {
	&dev_attr_register_brightness.attr,
	NULL,
};
ATTRIBUTE_GROUPS(ktz8866);

'''
text = once(text, 'static int ktz8866_probe(struct i2c_client *i2c)',
            telemetry + 'static int ktz8866_probe(struct i2c_client *i2c)')
text = once(text, '\t\t.of_match_table = ktz8866_match_table,',
            '\t\t.of_match_table = ktz8866_match_table,\n\t\t.dev_groups = ktz8866_groups,')
text = once(text, '\tint ret = 0;\n\n\tif (!i2c_check_functionality',
    '\tunsigned int enable;\n\tint ret;\n\n\tif (!i2c_check_functionality')
text = once(text, '''	if(!pdata->regmap) {
		pr_err("init regmap failed\\n");
		ret = -EINVAL;
	}''', '''	if (IS_ERR(pdata->regmap))
		return PTR_ERR(pdata->regmap);
	ret = regmap_read(pdata->regmap, KTZ8866_DISP_BL_ENABLE, &enable);
	if (ret)
		return ret;
	pdata->ktz8866_status = !!(enable & KTZ8866_backlight_EN_MASK);
	pdata->level = -1;
	pdata->dev = &i2c->dev;
	i2c_set_clientdata(i2c, pdata);''')
text = once(text, '\tlist_add(&pdata->entry, &ktz8866_dev_list);',
    '\tmutex_lock(&ktz8866_dev_list_mutex);\n\tlist_add(&pdata->entry, &ktz8866_dev_list);\n\tmutex_unlock(&ktz8866_dev_list_mutex);')
text = once(text, '\ti2c_set_clientdata(i2c, pdata);\n\tpdata->ops = &ops;',
'''\ti2c_set_clientdata(i2c, pdata);
\tpdata->ops = &ops;
\t/* Continuous splash may skip dsi_panel_reset entirely. Darken the LEDs
\t * at their own probe, before display reconfiguration; keep LCD bias on.
\t * Normal N81A backlight updates restore the user's requested level. */
\t{
\t\tconst char *model;
\t\tif (!of_property_read_string(of_root, "model", &model) &&
\t\t    !strcmp(model, "Qualcomm Technologies, Inc. 8550 sheng")) {
\t\t\tunsigned int lsb, msb, current_enable;
\t\t\tret = ktz_update_status(pdata, 0);
\t\t\tif (!ret)
\t\t\t\tret = regmap_read(pdata->regmap, KTZ8866_DISP_BB_LSB, &lsb);
\t\t\tif (!ret)
\t\t\t\tret = regmap_read(pdata->regmap, KTZ8866_DISP_BB_MSB, &msb);
\t\t\tif (!ret)
\t\t\t\tret = regmap_read(pdata->regmap, KTZ8866_DISP_BL_ENABLE, &current_enable);
\t\t\tif (ret)
\t\t\t\treturn ret;
\t\t\tdev_info(&i2c->dev, "sheng_backlight boot_dark actual=%u enable=0x%x previous_enable=0x%x\\n",
\t\t\t\t ((msb & 0xff) << 3) | (lsb & 7), current_enable, enable);
\t\t}
\t}''')
text = once(text, '''static int ktz8866_remove(struct i2c_client *i2c)
{
	return 0;
}''', '''static void ktz8866_remove(struct i2c_client *i2c)
{
	struct ktz8866_led *pdata = i2c_get_clientdata(i2c);

	mutex_lock(&ktz8866_dev_list_mutex);
	list_del(&pdata->entry);
	mutex_unlock(&ktz8866_dev_list_mutex);
}''')
text = once(text, '''int mi_backlight_ktz8866_init(void)
{
	INIT_LIST_HEAD(&ktz8866_dev_list);
	mutex_init(&ktz8866_dev_list_mutex);
	return i2c_add_driver(&ktz8866_driver);
}''', '''int sheng_ktz8866_init(void)
{
	return i2c_add_driver(&ktz8866_driver);
}

void sheng_ktz8866_exit(void)
{
	i2c_del_driver(&ktz8866_driver);
}''')
files[name] = text
name = display + 'msm/Kbuild'
files[name] = read(name) + '\nmsm_drm-y += sheng_ktz8866.o\n'
name = display + 'msm/msm_drv.c'
text = read(name)
text = '#include "sheng_ktz8866.h"\n' + text
text = once(text, 'static int __init msm_drm_register(void)\n{',
    'static int __init msm_drm_register(void)\n{\n\tint ret;')
text = once(text, '\tsde_rsc_rpmh_register();',
    '\tret = sheng_ktz8866_init();\n\tif (ret)\n\t\treturn ret;\n\n\tsde_rsc_rpmh_register();')
text = once(text, '\tplatform_driver_unregister(&msm_platform_driver);',
    '\tplatform_driver_unregister(&msm_platform_driver);\n\tsheng_ktz8866_exit();')
files[name] = text
name = display + 'msm/dsi/dsi_panel.c'
text = read(name)
text = '#include "../sheng_ktz8866.h"\n' + text
text = once(text, '\tint i;\n\n#ifdef OPLUS_FEATURE_DISPLAY\n\tDSI_INFO("dsi_panel_reset\\n");',
    '\tint i;\n\n'
    '\t/* Keep the N81A LCD dark while its reset invalidates the scanout.\n'
    '\t * Brightness is restored through the normal commit/backlight path.\n'
    '\t * 0x3f disables LEDs only; the original LCD bias bits stay enabled. */\n'
    '\tif (dsi_panel_is_sheng(panel) && panel->bl_config.type == DSI_BACKLIGHT_EXTERNAL) {\n'
    '\t\trc = ktz8866_backlight_update_status(0);\n'
    '\t\tif (rc)\n'
    '\t\t\treturn rc;\n'
    '\t}\n\n#ifdef OPLUS_FEATURE_DISPLAY\n\tDSI_INFO("dsi_panel_reset\\n");')
a = text.index('int dsi_panel_set_backlight(')
b = text.index('\n}\n', a) + 3
body = once(text[a:b], '\tcase DSI_BACKLIGHT_EXTERNAL:\n\t\tbreak;',
    '\tcase DSI_BACKLIGHT_EXTERNAL:\n\t\tif (dsi_panel_is_sheng(panel))\n\t\t\trc = ktz8866_backlight_update_status(bl_lvl);\n\t\tbreak;')
text = text[:a] + body + text[b:]
files[name] = text

diff, hashes = [], {}
for name, after in files.items():
    saved = backup / name
    before = saved.read_text() if saved.exists() else ''
    current = K618 / name
    assert not current.exists() or current.read_text() in (before, after) or sha(current.read_bytes()) == prior.get(name, {}).get('after'), 'Source drift: ' + name
    hashes[name] = dict(before=sha(before.encode()), after=sha(after.encode()), added=not saved.exists())
    diff.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile='a/' + name if saved.exists() else '/dev/null', tofile='b/' + name))
for name, after in files.items():
    (K618 / name).write_text(after)
(PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-camera-backlight.patch').write_text(''.join(diff))
refs = {}
for key, path in [('display', ROOT/'src/micode-display'), ('camera', ROOT/'src/micode-camera'),
                  ('los_nuwa_camera', ROOT/'src/lineage-modules')]:
    refs[key] = subprocess.check_output(['git', '-C', path, 'rev-parse', 'HEAD'], text=True).strip()
(PROJECT / 'reports/kernel618-camera-backlight-source.json').write_text(json.dumps(dict(
    references=refs, files=hashes,
    evidence='r24 CAM Invalid Seq type 14; stock N81A external backlight with two ktz,ktz8866 nodes',
    applicability='LOS nuwa and MiCode sheng agree BOB=13 BOB2=14; reuse same regulator path. LCD external backlight differs from phone DCS.',
    preserved='Official 2048-entry brightness remap, bias bits and voltage validation; stock DT and firmware unchanged',
    adaptation='6.18 I2C API, locked list lifetime, error propagation, program brightness before enabling LEDs',
    hardware_result='pending'), indent=2) + '\n')
print('Prepared sheng camera BOB ABI and KTZ8866 backlight')
