#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Retain sheng's active firmware PLL and MDP gate until consumers bind."""
import difflib
from build_sheng618_upstream import K618, PROJECT

path = K618 / 'soc/drivers/clk/qcom/dispcc-kalama.c'
before = path.read_text()
text = before

def replace(old, new):
    global text
    if new in text:
        return
    assert text.count(old) == 1, old[:100]
    text = text.replace(old, new, 1)

helper = '''/* The shipping DT uses generic kalama-mtp compatible strings. Match the
 * exact tablet model before preserving its already-running LCD scanout. */
static bool sheng_dispcc_live_splash;

static bool sheng_dispcc_board(void)
{
	const char *model;

	return !of_property_read_string(of_root, "model", &model) &&
		!strcmp(model, "Qualcomm Technologies, Inc. 8550 sheng");
}

/* Match the downstream Lucid OLE running test before *any* PLL writes.
 * ACK's helper enables all outputs before testing whether the PLL is live.
 * Retain the firmware's output mask, calibration and dividers for splash. */
static int sheng_dispcc_configure_pll(struct device *dev,
		struct clk_alpha_pll *pll, struct regmap *regmap,
		const struct alpha_pll_config *config)
{
	unsigned int mode, opmode;
	int ret;

	if (sheng_dispcc_live_splash) {
		ret = regmap_read(regmap, pll->offset, &mode);
		if (ret)
			return ret;
		ret = regmap_read(regmap,
			pll->offset + pll->regs[PLL_OFF_OPMODE], &opmode);
		if (ret)
			return ret;
		if ((mode & BIT(0)) && (opmode & BIT(0))) {
			dev_info(dev, "sheng_dispcc: retain live PLL%x mode=%x opmode=%x\\n",
				pll->offset, mode, opmode);
			return 0;
		}
	}
	clk_lucid_ole_pll_configure(pll, regmap, config);
	return 0;
}

'''
replace('static int disp_cc_kalama_probe(struct platform_device *pdev)\n',
        helper + 'static int disp_cc_kalama_probe(struct platform_device *pdev)\n')
replace('\tstruct regmap *regmap;\n\tint ret;\n\n\tregmap = qcom_cc_map',
        '\tstruct regmap *regmap;\n\tunsigned int mdp_branch;\n\tint ret;\n\n\tregmap = qcom_cc_map')
replace('''	sheng_dispcc_trace(&pdev->dev, "firmware");
	clk_lucid_ole_pll_configure(&disp_cc_pll0, regmap, &disp_cc_pll0_config);
	clk_lucid_ole_pll_configure(&disp_cc_pll1, regmap, &disp_cc_pll1_config);''', '''	sheng_dispcc_trace(&pdev->dev, "firmware");
	ret = regmap_read(regmap, 0x800c, &mdp_branch);
	if (ret)
		goto put_runtime;
	sheng_dispcc_live_splash = sheng_dispcc_board() && (mdp_branch & BIT(0));
	if (sheng_dispcc_live_splash)
		disp_cc_mdss_mdp_clk_src.flags &= ~HW_CLK_CTRL_MODE;
	ret = sheng_dispcc_configure_pll(&pdev->dev, &disp_cc_pll0,
		regmap, &disp_cc_pll0_config);
	if (ret)
		goto put_runtime;
	ret = sheng_dispcc_configure_pll(&pdev->dev, &disp_cc_pll1,
		regmap, &disp_cc_pll1_config);
	if (ret)
		goto put_runtime;''')
replace('\tregmap_update_bits(regmap, DISP_CC_MISC_CMD, 0x10, 0x10);',
        '\tif (!sheng_dispcc_live_splash)\n\t\tregmap_update_bits(regmap, DISP_CC_MISC_CMD, 0x10, 0x10);')
replace('''static void disp_cc_kalama_sync_state(struct device *dev)
{
	qcom_cc_sync_state(dev, &disp_cc_kalama_desc);
}''', '''static void disp_cc_kalama_sync_state(struct device *dev)
{
	struct regmap *map;
	int ret;

	if (sheng_dispcc_live_splash) {
		ret = pm_runtime_resume_and_get(dev);
		if (ret < 0) {
			dev_err(dev, "failed to finish splash clock takeover: %d\\n", ret);
			return;
		}
		map = dev_get_regmap(dev, NULL);
		ret = regmap_update_bits(map, DISP_CC_MISC_CMD, BIT(4), BIT(4));
		if (ret) {
			dev_err(dev, "failed to restore MDP gating: %d\\n", ret);
			pm_runtime_put_sync(dev);
			return;
		}
		/* Future normal rate updates may select hardware control. Avoid
		 * a forced live RCG update solely to change its gating mode. */
		disp_cc_mdss_mdp_clk_src.flags |= HW_CLK_CTRL_MODE;
		sheng_dispcc_trace(dev, "consumers-bound");
		sheng_dispcc_live_splash = false;
		qcom_cc_sync_state(dev, &disp_cc_kalama_desc);
		pm_runtime_put_sync(dev);
		return;
	}
	qcom_cc_sync_state(dev, &disp_cc_kalama_desc);
}''')
if text != before:
    patch = ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
        fromfile='a/soc/drivers/clk/qcom/dispcc-kalama.c',
        tofile='b/soc/drivers/clk/qcom/dispcc-kalama.c'))
    (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-dispcc-live.patch').write_text(patch)
    path.write_text(text)
print('Sheng live PLL outputs and MDP gates retained until display consumers bind')
