#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read sheng's live scanout state across display clocks and SMMU takeover."""
import difflib
from build_sheng618_upstream import K618, PROJECT

paths = [K618 / 'soc/drivers/clk/qcom/dispcc-kalama.c',
         K618 / 'soc/drivers/iommu/arm/arm-smmu/arm-smmu.c']
patch = []
for path in paths:
    before = path.read_text()
    text = before
    include = '#include "sheng_early_scan_trace.h"\n'
    if include not in text:
        anchor = '#include <linux/of.h>\n'
        assert text.count(anchor) == 1
        text = text.replace(anchor, anchor + include, 1)
    if path.name == 'dispcc-kalama.c':
        old = '\tif (!map)\n\t\treturn;\n\tfor (i = 0; i < ARRAY_SIZE(regs); i++)'
        new = '\tsheng_early_scan_trace(stage);\n' + old
        if new not in text:
            assert text.count(old) == 1
            text = text.replace(old, new, 1)
        old = '\tpm_runtime_put_sync(&pdev->dev);\n\tdev_info(&pdev->dev, "Registered DISP CC clocks\\n");'
        new = '\tpm_runtime_put_sync(&pdev->dev);\n\tsheng_early_scan_trace("clock-runtime-released");\n\tdev_info(&pdev->dev, "Registered DISP CC clocks\\n");'
        if new not in text:
            assert text.count(old) == 1
            text = text.replace(old, new, 1)
    else:
        old = '''static void sheng_smmu_trace_streams(struct arm_smmu_device *smmu,
		const char *stage)
{
	unsigned int i;

	for (i = 0; i < smmu->num_mapping_groups; i++)'''
        new = old.replace('\n\tfor (i', '\n\tif (smmu->smrs && sheng_smmu_firmware_bypass_active(smmu))\n\t\tsheng_early_scan_trace(stage);\n\tfor (i', 1)
        if new not in text:
            assert text.count(old) == 1
            text = text.replace(old, new, 1)
    patch.extend(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
        fromfile='a/' + str(path.relative_to(K618)),
        tofile='b/' + str(path.relative_to(K618))))
    path.write_text(text)
    (path.parent / 'sheng_early_scan_trace.h').write_bytes(
        (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng_early_scan_trace.h').read_bytes())
if patch:
    (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-early-scan-trace.patch').write_text(''.join(patch))
print('Read-only DT scanout snapshots at existing powered handoff sites; zero waits')
