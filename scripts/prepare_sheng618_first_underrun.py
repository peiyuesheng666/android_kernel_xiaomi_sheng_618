#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Opt-in bounded read-only capture of the first pre-display underrun."""
import difflib
from build_sheng618_upstream import K618, PROJECT

path = K618 / 'soc/drivers/iommu/arm/arm-smmu/arm-smmu.c'
before = path.read_text()
text = before

def replace(old, new):
    global text
    if new in text:
        return
    assert text.count(old) == 1, old[:100]
    text = text.replace(old, new, 1)

replace('#include <linux/wait.h>\n', '#include <linux/wait.h>\n#include <linux/workqueue.h>\n')
marker = 'static void sheng_smmu_trace_streams(struct arm_smmu_device *smmu,\n'
watch = '''/* No boot hold or register writes. Sample for at most three seconds,
 * then stop on the first underrun, lost power/clock access, or deadline. */
static unsigned int sheng_scan_watch_ms;
module_param(sheng_scan_watch_ms, uint, 0400);
MODULE_PARM_DESC(sheng_scan_watch_ms, "Diagnostic first-underrun watch, 0 disables, max 3000 ms");
static bool sheng_scan_watch_started;
static ktime_t sheng_scan_watch_deadline;
static void sheng_scan_watch_poll(struct work_struct *work);
static DECLARE_DELAYED_WORK(sheng_scan_watch_work, sheng_scan_watch_poll);

static void sheng_scan_watch_poll(struct work_struct *work)
{
	u32 status = 0;
	int ret;

	if (ktime_compare(ktime_get(), sheng_scan_watch_deadline) >= 0) {
		pr_info("sheng early scan: watch deadline reached without underrun\\n");
		return;
	}
	ret = sheng_early_scan_probe("watch", false, &status);
	if (ret) {
		pr_info("sheng early scan: watch stopped, access=%d\\n", ret);
		sheng_early_scan_trace("watch-access-ended");
		return;
	}
	if (status & (BIT(26) | BIT(28))) {
		pr_info("sheng early scan: first-underrun status=%x\\n", status);
		sheng_early_scan_trace("first-underrun");
		return;
	}
	queue_delayed_work(system_unbound_wq, &sheng_scan_watch_work,
		msecs_to_jiffies(10));
}

static void sheng_scan_watch_start(void)
{
	if (!sheng_scan_watch_ms || sheng_scan_watch_started)
		return;
	if (sheng_scan_watch_ms > 3000) {
		pr_err("sheng early scan: invalid watch duration %u\\n", sheng_scan_watch_ms);
		return;
	}
	sheng_scan_watch_started = true;
	sheng_scan_watch_deadline = ktime_add_ms(ktime_get(), sheng_scan_watch_ms);
	pr_info("sheng early scan: bounded watch armed for %u ms\\n", sheng_scan_watch_ms);
	queue_delayed_work(system_unbound_wq, &sheng_scan_watch_work, 0);
}

'''
replace(marker, watch + marker)
replace('''	if (smmu->smrs && sheng_smmu_firmware_bypass_active(smmu))
		sheng_early_scan_trace(stage);
	for (i = 0; i < smmu->num_mapping_groups; i++)''', '''	if (smmu->smrs && sheng_smmu_firmware_bypass_active(smmu)) {
		sheng_early_scan_trace(stage);
		if (sheng_smmu_board() && !strcmp(stage, "context-deferred"))
			sheng_scan_watch_start();
	}
	for (i = 0; i < smmu->num_mapping_groups; i++)''')
replace('''static void __exit arm_smmu_exit(void)
{
	platform_driver_unregister''', '''static void __exit arm_smmu_exit(void)
{
	cancel_delayed_work_sync(&sheng_scan_watch_work);
	platform_driver_unregister''')
if text != before:
    (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-first-underrun.patch').write_text(
        ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
            fromfile='a/soc/drivers/iommu/arm/arm-smmu/arm-smmu.c',
            tofile='b/soc/drivers/iommu/arm/arm-smmu/arm-smmu.c')))
    path.write_text(text)
for directory in (path.parent, K618 / 'soc/drivers/clk/qcom'):
    (directory / 'sheng_early_scan_trace.h').write_bytes(
        (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng_early_scan_trace.h').read_bytes())
print('Opt-in first-underrun capture staged: default 0, max 3000 ms, no hold or hardware writes')
