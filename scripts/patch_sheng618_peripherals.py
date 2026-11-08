#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Wire the actual sheng pen charge events, TDDI retention and six speaker amps."""
import difflib
import hashlib
import json
from build_sheng618_upstream import ROOT, PROJECT, K618

backup = ROOT / 'diagnostic/peripherals-r21/source-before'
changes = {}
def get(name):
    path = K618/name
    saved = backup/name
    if not saved.exists():
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(path.read_bytes())
    return saved.read_text()
def once(text, old, new):
    assert text.count(old) == 1, old[:100]
    return text.replace(old, new, 1)

name = 'soc/drivers/power/supply/qti_battery_charger.c'
text = get(name)
text = once(text, 'static void handle_notification(', '''/* sheng: MiCode pen docking notifications (real XM hall properties). */
static ATOMIC_NOTIFIER_HEAD(pen_charge_state_notifier);
int pen_charge_state_notifier_register_client(struct notifier_block *nb);
int pen_charge_state_notifier_unregister_client(struct notifier_block *nb);

static void sheng_pen_notifier_work(struct work_struct *work)
{
	struct battery_chg_dev *bcdev = container_of(work, struct battery_chg_dev,
		sheng_pen_work);
	struct psy_state *pst = &bcdev->psy_list[PSY_TYPE_XM];
	int rc, attached;

	rc = read_property_id(bcdev, pst, XM_PROP_PEN_HALL3);
	if (rc)
		return;
	rc = read_property_id(bcdev, pst, XM_PROP_PEN_HALL4);
	if (rc)
		return;
	attached = !(!!pst->prop[XM_PROP_PEN_HALL3] & !!pst->prop[XM_PROP_PEN_HALL4]);
	if (attached != bcdev->sheng_pen_last) {
		bcdev->sheng_pen_last = attached;
		atomic_notifier_call_chain(&pen_charge_state_notifier, attached, NULL);
	}
}

int pen_charge_state_notifier_register_client(struct notifier_block *nb)
{
	struct power_supply *psy;
	struct battery_chg_dev *bcdev;
	int ret = atomic_notifier_chain_register(&pen_charge_state_notifier, nb);

	if (ret)
		return ret;
	psy = power_supply_get_by_name("battery");
	if (psy) {
		bcdev = power_supply_get_drvdata(psy);
		if (bcdev && of_machine_is_compatible("qcom,kalama-sheng"))
			schedule_work(&bcdev->sheng_pen_work);
		power_supply_put(psy);
	}
	return 0;
}
EXPORT_SYMBOL(pen_charge_state_notifier_register_client);

int pen_charge_state_notifier_unregister_client(struct notifier_block *nb)
{
	return atomic_notifier_chain_unregister(&pen_charge_state_notifier, nb);
}
EXPORT_SYMBOL(pen_charge_state_notifier_unregister_client);

static void handle_notification(''')
# The live DT root compatible is checked by the preparation script below.
dt = (ROOT/'diagnostic/disklog-r5/live.dts').read_text()
compatible_line = next(line for line in dt.splitlines() if 'compatible =' in line)
# Root Qualcomm boards commonly omit the product name; use the exact observed root below.
print('Live root:', compatible_line.strip())
text = text.replace('bcdev && of_machine_is_compatible("qcom,kalama-sheng")', 'bcdev && bcdev->sheng_has_pen')
text = once(text, '\tint\t\t\tk618_panel_tries;',
    '\tstruct work_struct sheng_pen_work;\n\tint sheng_pen_last;\n\tbool sheng_has_pen;\n\tint\t\t\tk618_panel_tries;')
text = once(text, '\t\tschedule_delayed_work(&bcdev->xm_prop_change_work, 0);\n\t\tbreak;',
    '\t\tschedule_delayed_work(&bcdev->xm_prop_change_work, 0);\n'
    '\t\tif (bcdev->sheng_has_pen)\n\t\t\tschedule_work(&bcdev->sheng_pen_work);\n\t\tbreak;')
text = once(text, '\tINIT_WORK(&bcdev->subsys_up_work, battery_chg_subsys_up_work);',
    '''	INIT_WORK(&bcdev->sheng_pen_work, sheng_pen_notifier_work);
	bcdev->sheng_pen_last = -1;
	/* Identify sheng by its unique panel, not a phone root compatible. */
	{
		struct device_node *np;
		u64 id;
		for_each_node_with_property(np, "mi,panel-id") {
			if (!of_property_read_u64(np, "mi,panel-id", &id) &&
			    id == 0x4e38316150360200ULL) {
				bcdev->sheng_has_pen = true;
				of_node_put(np);
				break;
			}
		}
	}
	INIT_WORK(&bcdev->subsys_up_work, battery_chg_subsys_up_work);''')
anchor = '\trc = pmic_glink_unregister_client(bcdev->client);'
# Add cleanup only to remove, after the producer is unregistered.
a = text.index('static void battery_chg_remove(')
b = text.index('\n}\n', a)
body = text[a:b]
body = once(body, '\tif (rc < 0)\n\t\tpr_err("Error unregistering from pmic_glink, rc=%d\\n", rc);',
    '\tif (rc < 0)\n\t\tpr_err("Error unregistering from pmic_glink, rc=%d\\n", rc);\n\tcancel_work_sync(&bcdev->sheng_pen_work);')
text = text[:a]+body+text[b:]
changes[name] = text

name = 'vendor/qcom/opensource/display-drivers/msm/dsi/dsi_panel.h'
text = get(name)
text = once(text, '\tbool panel_initialized;', '\tbool panel_initialized;\n\tbool sheng_power_retained;')
text = once(text, 'bool dsi_panel_is_sheng(struct dsi_panel *panel);',
    'bool dsi_panel_is_sheng(struct dsi_panel *panel);\nvoid dsi_panel_gesture_enable(bool on);')
changes[name] = text
name = 'vendor/qcom/opensource/display-drivers/msm/dsi/dsi_panel.c'
text = get(name)
a = text.index('int dsi_panel_power_on(')
b = text.index('\nint dsi_panel_power_off(', a)
body = text[a:b]
body = once(body, '\trc = dsi_pwr_enable_regulator(&panel->power_info, true);',
    '\tif (!panel->sheng_power_retained)\n\t\trc = dsi_pwr_enable_regulator(&panel->power_info, true);\n\tpanel->sheng_power_retained = false;')
text = text[:a]+body+text[b:]
a = text.index('int dsi_panel_power_off(')
b = text.index('\n}\n', a)+3
body = text[a:b]
body = once(body, '\tint rc = 0;',
    '\tint rc = 0;\n\tbool keep_touch = dsi_panel_is_sheng(panel) && READ_ONCE(sheng_gesture_enabled) &&\n\t\t!atomic_read(&panel->esd_recovery_pending);')
body = once(body, 'if (gpio_is_valid(panel->reset_config.reset_gpio) &&',
    'if (!keep_touch && gpio_is_valid(panel->reset_config.reset_gpio) &&')
body = once(body, '\trc = dsi_pwr_enable_regulator(&panel->power_info, false);',
    '\tif (keep_touch)\n\t\tpanel->sheng_power_retained = true;\n\telse\n\t\trc = dsi_pwr_enable_regulator(&panel->power_info, false);')
text = text[:a]+body+text[b:]
text = once(text, 'int dsi_panel_power_on(', '''/* TDDI gesture mode keeps the touch controller's shared supply alive. */
static bool sheng_gesture_enabled;
void dsi_panel_gesture_enable(bool on)
{
	WRITE_ONCE(sheng_gesture_enabled, on);
}
EXPORT_SYMBOL(dsi_panel_gesture_enable);

int dsi_panel_power_on(''')
changes[name] = text

name = 'vendor/qcom/opensource/audio-kernel/asoc/kalama.c'
text = get(name)
text = once(text, 'static void k618_link_spk_amps(', '''/* MiCode sheng msm_dailink.h: the same six CS35L43 on secondary RX and TX.
 * CS35L43's own hw_params selects I2S/DSP_A and the PLL; do not run L41 setup.
 */
static int sheng_link_spk_amps(struct device *dev, struct snd_soc_card *card)
{
	struct snd_soc_dai_link_component *codecs;
	struct device_node *np;
	int i, n = 0;

	for_each_compatible_node(np, NULL, "cirrus,cs35l43")
		if (of_device_is_available(np))
			n++;
	if (!n)
		return 0;
	if (n != 6)
		return -EINVAL;
	codecs = devm_kcalloc(dev, n, sizeof(*codecs), GFP_KERNEL);
	if (!codecs)
		return -ENOMEM;
	i = 0;
	for_each_compatible_node(np, NULL, "cirrus,cs35l43") {
		struct snd_soc_dai_link_component dlc = {
			.of_node = np, .dai_name = "cs35l43-pcm",
		};
		if (!of_device_is_available(np))
			continue;
		if (!snd_soc_find_dai_with_mutex(&dlc)) {
			of_node_put(np);
			return -EPROBE_DEFER;
		}
		/* DT nodes are static for the lifetime of this board. */
		codecs[i++] = dlc;
	}
	for (i = 0; i < card->num_links; i++) {
		struct snd_soc_dai_link *link = &card->dai_link[i];
		if (link->name && (!strcmp(link->name, LPASS_BE_SEC_TDM_RX_0) ||
		    !strcmp(link->name, LPASS_BE_SEC_TDM_TX_0))) {
			link->codecs = codecs;
			link->num_codecs = n;
			link->ops = &msm_common_be_ops;
			dev_info(dev, "sheng: %d CS35L43 on %s\\n", n, link->name);
		}
	}
	return n;
}

static void k618_link_spk_amps(''')
text = once(text, '\tk618_link_spk_amps(&pdev->dev, card);',
    '\tret = sheng_link_spk_amps(&pdev->dev, card);\n\tif (ret < 0)\n\t\treturn ret;\n\tif (!ret)\n\t\tk618_link_spk_amps(&pdev->dev, card);')
changes[name] = text

diffs, hashes = [], {}
for name, text in changes.items():
    original = (backup/name).read_text()
    current = (K618/name).read_text()
    if name.endswith('/audio-kernel/asoc/kalama.c') and current != text:
        a = original.index('/*\n * k618: the speakers.')
        b = original.index('static int msm_dmic_event(', a)
        block = original[a:b]
        if current.count(block) == 1:
            current = current.replace(block, '', 1)
        current = current.replace('\tk618_link_spk_amps(&pdev->dev, card);\n\tret = sheng_link_spk_amps',
                                  '\tret = sheng_link_spk_amps', 1)
        if current not in (original, text):
            print(''.join(difflib.unified_diff(text.splitlines(True), current.splitlines(True)))[:4000])
    assert current in (original, text), 'Unexpected source changes: '+name
    hashes[name] = dict(before=hashlib.sha256(original.encode()).hexdigest(),
                        after=hashlib.sha256(text.encode()).hexdigest())
    diffs.extend(difflib.unified_diff(original.splitlines(True), text.splitlines(True),
        fromfile='a/'+name, tofile='b/'+name, n=3))
for name, text in changes.items():
    (K618/name).write_text(text)
(PROJECT/'device/xiaomi/sheng/interfaces/kernel/6.18/peripherals.patch').write_text(''.join(diffs))
(PROJECT/'reports/kernel618-peripherals-source.json').write_text(json.dumps(dict(
    references=dict(kernel='MiCode sheng 29db5d59', display='6461221b68908b990e1fa2b60feaa812cb944ef5',
                    audio='MiCode sheng msm_dailink.h CONFIG_TARGET_PRODUCT_SHENG'),
    files=hashes, runtime_verified=False), indent=2)+'\n')
print('Applied pen/TDDI/CS35L43 wiring')
