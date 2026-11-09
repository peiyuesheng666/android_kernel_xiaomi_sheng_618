#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Retain sheng firmware bypass shareability until the pinned Linux map is live."""
import difflib
from build_sheng618_upstream import K618, PROJECT

tree = K618 / 'soc/drivers/iommu/arm/arm-smmu'
path = tree / 'arm-smmu.c'
before = path.read_text()
text = before

def replace(old, new):
    global text
    if new in text:
        return
    assert text.count(old) == 1, old[:100]
    text = text.replace(old, new, 1)

marker = 'static void sheng_smmu_trace_streams(struct arm_smmu_device *smmu,\n'
helpers = '''static bool sheng_smmu_board(void)
{
	struct device_node *root = of_find_node_by_path("/");
	const char *model;
	bool sheng = root && !of_property_read_string(root, "model", &model) &&
		!strcmp(model, "Qualcomm Technologies, Inc. 8550 sheng");

	of_node_put(root);
	return sheng;
}

static void sheng_smmu_finish_global_handoff(struct arm_smmu_device *smmu)
{
	u32 reg, next;

	if (!sheng_smmu_board() || sheng_smmu_firmware_bypass_active(smmu))
		return;
	reg = arm_smmu_gr0_read(smmu, ARM_SMMU_GR0_sCR0);
	next = (reg & ~ARM_SMMU_sCR0_SHCFG) |
		FIELD_PREP(ARM_SMMU_sCR0_SHCFG, ARM_SMMU_sCR0_SHCFG_NSH);
	if (next == reg)
		return;
	arm_smmu_gr0_write(smmu, ARM_SMMU_GR0_sCR0, next);
	dev_info(smmu->dev,
		"sheng splash: Linux mapping live; global CR0=%x->%x\\n", reg, next);
}

'''
replace(marker, helpers + marker)
replace('''	/* Force bypass transaction to be Non-Shareable & not io-coherent */
	reg &= ~ARM_SMMU_sCR0_SHCFG;
	reg |= FIELD_PREP(ARM_SMMU_sCR0_SHCFG, ARM_SMMU_sCR0_SHCFG_NSH);''', '''	/* A pinned firmware context with M=0 still scans out using bypass.
	 * Preserve its global memory attributes even after Linux allocates an
	 * EARLY_MAP context; switch once every pinned Linux context has M=1. */
	if (sheng_smmu_board() && sheng_smmu_firmware_bypass_active(smmu)) {
		dev_info(dev, "sheng splash: retain firmware global SHCFG in CR0=%x\\n", reg);
	} else {
		reg &= ~ARM_SMMU_sCR0_SHCFG;
		reg |= FIELD_PREP(ARM_SMMU_sCR0_SHCFG, ARM_SMMU_sCR0_SHCFG_NSH);
	}''')
replace('''			idx, cb->sctlr);
		sheng_smmu_trace_streams(smmu, "mappings-after-install");''', '''			idx, cb->sctlr);
		/* Context-bank writes precede changing attributes for bypass. */
		wmb();
		sheng_smmu_finish_global_handoff(smmu);
		sheng_smmu_trace_streams(smmu, "mappings-after-install");''')
if text != before:
    (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-smmu-global-handoff.patch').write_text(
        ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
            fromfile='a/soc/drivers/iommu/arm/arm-smmu/arm-smmu.c',
            tofile='b/soc/drivers/iommu/arm/arm-smmu/arm-smmu.c')))
    path.write_text(text)
(tree / 'sheng_smmu_handoff.h').write_bytes(
    (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng_smmu_handoff.h').read_bytes())
print('Exact sheng model: global bypass SHCFG retained until pinned mappings are live')
