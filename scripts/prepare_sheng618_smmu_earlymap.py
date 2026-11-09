#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Preserve firmware bypass attributes until splash mappings are ready."""
import difflib
import shutil
from build_sheng618_upstream import K618, PROJECT

directory = K618 / 'soc/drivers/iommu/arm/arm-smmu'
shutil.copyfile(PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng_smmu_handoff.h',
                directory / 'sheng_smmu_handoff.h')
path = directory / 'arm-smmu.c'
before = path.read_text()
text = before

def replace(old, new):
    global text
    if new in text:
        return
    assert text.count(old) == 1, old[:100]
    text = text.replace(old, new, 1)

replace('\tarm_smmu_init_context_bank(smmu_domain, pgtbl_cfg);\n\tif (smmu->impl && smmu->impl->init_context_bank)\n\t\tsmmu->impl->init_context_bank(smmu_domain, dev);\n\tarm_smmu_write_context_bank(smmu, cfg->cbndx);', '''	arm_smmu_init_context_bank(smmu_domain, pgtbl_cfg);
	if (sheng_smmu_defer_boot_context(smmu, cfg->cbndx,
			smmu_domain->delayed_s1_trans_enable,
			cfg->cbar != CBAR_TYPE_S2_TRANS)) {
		/* Even with M=0, Linux's coherent-bypass attributes change the
		 * firmware scanout's memory accesses. Store Linux's new tables
		 * in RAM, but leave the live hardware context alone until the
		 * display explicitly enables translation after mapping splash. */
		dev_info(smmu->dev,
			"sheng splash: defer CB%u context; firmware SCTLR=%x Linux bypass=%x\\n",
			cfg->cbndx,
			arm_smmu_cb_read(smmu, cfg->cbndx, ARM_SMMU_CB_SCTLR),
			smmu->cbs[cfg->cbndx].sctlr);
	} else {
		if (smmu->impl && smmu->impl->init_context_bank)
			smmu->impl->init_context_bank(smmu_domain, dev);
		arm_smmu_write_context_bank(smmu, cfg->cbndx);
	}''')
replace('\tarm_smmu_cb_write(smmu, idx, ARM_SMMU_CB_SCTLR, cb->sctlr);\n\tarm_smmu_rpm_put(smmu);\n\tsmmu_domain->delayed_s1_trans_enable = false;', '''	if (sheng_smmu_context_has_pinned_stream(smmu, idx)) {
		/* This EARLY_MAP context was deferred at allocation. Install
		 * CBA2R/CBAR, TCR, TTBR and MAIR before the final SCTLR.M write. */
		if (smmu->impl && smmu->impl->init_context_bank)
			smmu->impl->init_context_bank(smmu_domain, smmu_domain->dev);
		arm_smmu_write_context_bank(smmu, idx);
		dev_info(smmu->dev,
			"sheng splash: mappings ready; installed CB%d SCTLR=%x\\n",
			idx, cb->sctlr);
	} else {
		arm_smmu_cb_write(smmu, idx, ARM_SMMU_CB_SCTLR, cb->sctlr);
	}
	arm_smmu_rpm_put(smmu);
	smmu_domain->delayed_s1_trans_enable = false;''')
if text != before:
    (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-smmu-earlymap.patch').write_text(
        ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
            fromfile='a/soc/drivers/iommu/arm/arm-smmu/arm-smmu.c',
            tofile='b/soc/drivers/iommu/arm/arm-smmu/arm-smmu.c')))
    path.write_text(text)
print('Pinned EARLY_MAP context deferred until all splash mappings exist', flush=True)
