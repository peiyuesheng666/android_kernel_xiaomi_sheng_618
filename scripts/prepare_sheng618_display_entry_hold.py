#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Add an opt-in hold before any display driver hardware registration."""
import difflib
from build_sheng618_upstream import K618, PROJECT

path = K618 / 'vendor/qcom/opensource/display-drivers/msm/msm_drv.c'
before = path.read_text()
text = before
marker = 'static int __init msm_drm_register(void)\n'
if 'static unsigned int sheng_before_display_hold_ms;' not in text:
    assert text.count(marker) == 1
    text = text.replace(marker, '''static unsigned int sheng_before_display_hold_ms;
module_param(sheng_before_display_hold_ms, uint, 0400);
MODULE_PARM_DESC(sheng_before_display_hold_ms, "Test-only display entry hold, 0 disables, max 10000 ms");

''' + marker, 1)
old = '''	if (!modeset)
		return -EINVAL;

	DBG("init");'''
new = '''	if (!modeset)
		return -EINVAL;
	if (sheng_before_display_hold_ms > 10000)
		return -EINVAL;
	if (sheng_before_display_hold_ms) {
		pr_notice("TEST_ONLY before-display hold begin (%u ms)\\n",
			sheng_before_display_hold_ms);
		msleep(sheng_before_display_hold_ms);
		pr_notice("TEST_ONLY before-display hold end\\n");
	}

	DBG("init");'''
if new not in text:
    assert text.count(old) == 1
    text = text.replace(old, new, 1)
if '#include <linux/delay.h>' not in text:
    marker = '#include "sheng_ktz8866.h"'
    assert text.count(marker) == 1
    text = text.replace(marker, marker + '\n#include <linux/delay.h>', 1)
if text != before:
    (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-display-entry-hold.patch').write_text(
        ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
            fromfile='a/vendor/qcom/opensource/display-drivers/msm/msm_drv.c',
            tofile='b/vendor/qcom/opensource/display-drivers/msm/msm_drv.c')))
    path.write_text(text)
print('Display entry hold staged before KTZ, SMMU and DSI registration; default zero')
