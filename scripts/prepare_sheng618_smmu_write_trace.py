#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Trace writes and live state for DT-pinned display streams without changing them."""
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

marker = 'void arm_smmu_write_context_bank(struct arm_smmu_device *smmu, int idx)\n'
helper = '''/* Read-only snapshots of the firmware's DT-pinned display stream.
 * The caller already has the SMMU powered; none of these registers clear
 * status on read. Do not dump ordinary clients or change handoff policy. */
static void sheng_smmu_trace_streams(struct arm_smmu_device *smmu,
		const char *stage)
{
	unsigned int i;

	for (i = 0; i < smmu->num_mapping_groups; i++) {
		struct arm_smmu_s2cr *s2cr = &smmu->s2crs[i];
		unsigned int cbndx = s2cr->cbndx;

		if (!s2cr->pinned || cbndx >= smmu->num_context_banks)
			continue;
		dev_info(smmu->dev,
			"sheng smmu trace: %s SMR%u=%x S2CR=%x CB%u SCTLR=%x CBAR=%x CR0=%x linux_cfg=%u linux_sctlr=%x\\n",
			stage, i, arm_smmu_gr0_read(smmu, ARM_SMMU_GR0_SMR(i)),
			arm_smmu_gr0_read(smmu, ARM_SMMU_GR0_S2CR(i)), cbndx,
			arm_smmu_cb_read(smmu, cbndx, ARM_SMMU_CB_SCTLR),
			arm_smmu_gr1_read(smmu, ARM_SMMU_GR1_CBAR(cbndx)),
			arm_smmu_gr0_read(smmu, ARM_SMMU_GR0_sCR0),
			!!smmu->cbs[cbndx].cfg, smmu->cbs[cbndx].sctlr);
	}
}

'''
replace(marker, helper + marker)
replace('''	struct arm_smmu_cfg *cfg = cb->cfg;

	/* Unassigned context banks only need disabling */''', '''	struct arm_smmu_cfg *cfg = cb->cfg;

	if (sheng_smmu_context_has_pinned_stream(smmu, idx))
		dev_info(smmu->dev,
			"sheng smmu trace: write CB%d SCTLR=%x->%x cfg=%u caller=%pS\\n",
			idx, arm_smmu_cb_read(smmu, idx, ARM_SMMU_CB_SCTLR),
			cfg ? cb->sctlr : 0, !!cfg, __builtin_return_address(0));
	/* Unassigned context banks only need disabling */''')
replace('''	arm_smmu_gr0_write(smmu, ARM_SMMU_GR0_SMR(idx), reg);
}''', '''	if (smmu->s2crs[idx].pinned)
		dev_info(smmu->dev,
			"sheng smmu trace: write SMR%d %x->%x caller=%pS\\n",
			idx, arm_smmu_gr0_read(smmu, ARM_SMMU_GR0_SMR(idx)),
			reg, __builtin_return_address(0));
	arm_smmu_gr0_write(smmu, ARM_SMMU_GR0_SMR(idx), reg);
}''')
replace('''	arm_smmu_gr0_write(smmu, ARM_SMMU_GR0_S2CR(idx), reg);
}''', '''	if (s2cr->pinned)
		dev_info(smmu->dev,
			"sheng smmu trace: write S2CR%d %x->%x caller=%pS\\n",
			idx, arm_smmu_gr0_read(smmu, ARM_SMMU_GR0_S2CR(idx)),
			reg, __builtin_return_address(0));
	arm_smmu_gr0_write(smmu, ARM_SMMU_GR0_S2CR(idx), reg);
}''')
replace('''			smmu->cbs[cfg->cbndx].sctlr);
	} else {''', '''			smmu->cbs[cfg->cbndx].sctlr);
		sheng_smmu_trace_streams(smmu, "context-deferred");
	} else {''')
replace('''	if (sheng_smmu_context_has_pinned_stream(smmu, idx)) {
		/* This EARLY_MAP context''', '''	if (sheng_smmu_context_has_pinned_stream(smmu, idx)) {
		sheng_smmu_trace_streams(smmu, "mappings-before-install");
		/* This EARLY_MAP context''')
replace('''			idx, cb->sctlr);
	} else {''', '''			idx, cb->sctlr);
		sheng_smmu_trace_streams(smmu, "mappings-after-install");
	} else {''')
replace('''	/* clear global FSR */
	reg = arm_smmu_gr0_read''', '''	sheng_smmu_trace_streams(smmu, "reset-before");
	/* clear global FSR */
	reg = arm_smmu_gr0_read''')
replace('''	arm_smmu_gr0_write(smmu, ARM_SMMU_GR0_sCR0, reg);
}

static int arm_smmu_id_size_to_bits''', '''	arm_smmu_gr0_write(smmu, ARM_SMMU_GR0_sCR0, reg);
	sheng_smmu_trace_streams(smmu, "reset-after");
}

static int arm_smmu_id_size_to_bits''')
if text != before:
    (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-smmu-write-trace.patch').write_text(
        ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
            fromfile='a/soc/drivers/iommu/arm/arm-smmu/arm-smmu.c',
            tofile='b/soc/drivers/iommu/arm/arm-smmu/arm-smmu.c')))
    path.write_text(text)
print('Pinned-stream read-only state and actual register write tracing staged')
