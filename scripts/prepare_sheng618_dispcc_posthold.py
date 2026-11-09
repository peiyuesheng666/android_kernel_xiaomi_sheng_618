#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Add an opt-in timing hold after DISP CC registration and runtime handoff."""
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

replace('#include <linux/clk.h>\n', '#include <linux/clk.h>\n#include <linux/delay.h>\n')
replace('static bool sheng_dispcc_live_splash;\n', '''static bool sheng_dispcc_live_splash;
static unsigned int sheng_postclock_hold_ms;
module_param(sheng_postclock_hold_ms, uint, 0400);
MODULE_PARM_DESC(sheng_postclock_hold_ms, "Test-only post-DISP-CC hold, 0 disables, max 10000 ms");
''')
replace('\tregmap = qcom_cc_map(pdev, &disp_cc_kalama_desc);',
        '\tif (sheng_postclock_hold_ms > 10000)\n\t\treturn -EINVAL;\n\tregmap = qcom_cc_map(pdev, &disp_cc_kalama_desc);')
replace('''	dev_info(&pdev->dev, "Registered DISP CC clocks\\n");

	return ret;''', '''	dev_info(&pdev->dev, "Registered DISP CC clocks\\n");
	if (!ret && sheng_dispcc_board() && sheng_postclock_hold_ms) {
		dev_notice(&pdev->dev, "TEST_ONLY post-clock hold begin (%u ms)\\n",
			sheng_postclock_hold_ms);
		msleep(sheng_postclock_hold_ms);
		dev_notice(&pdev->dev, "TEST_ONLY post-clock hold end\\n");
	}

	return ret;''')
if text != before:
    (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-dispcc-posthold.patch').write_text(
        ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
            fromfile='a/soc/drivers/clk/qcom/dispcc-kalama.c',
            tofile='b/soc/drivers/clk/qcom/dispcc-kalama.c')))
    path.write_text(text)
print('Opt-in post-clock hold staged; default zero, range bounded, success path only')
