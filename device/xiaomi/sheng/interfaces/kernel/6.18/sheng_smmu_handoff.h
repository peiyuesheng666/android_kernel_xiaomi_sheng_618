/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SHENG_SMMU_HANDOFF_H
#define SHENG_SMMU_HANDOFF_H

/* SMR indices and context-bank indices are separate namespaces. */
static inline bool sheng_smmu_keep_firmware_smr(
		struct arm_smmu_device *smmu, unsigned int smendx)
{
	return smendx < smmu->num_mapping_groups &&
		smmu->s2crs[smendx].pinned &&
		smmu->s2crs[smendx].type == S2CR_TYPE_TRANS;
}

static inline bool sheng_smmu_context_has_pinned_stream(
		struct arm_smmu_device *smmu, unsigned int cbndx)
{
	unsigned int i;

	if (cbndx >= smmu->num_context_banks)
		return false;
	for (i = 0; i < smmu->num_mapping_groups; i++) {
		if (smmu->s2crs[i].pinned &&
		    smmu->s2crs[i].type == S2CR_TYPE_TRANS &&
		    smmu->s2crs[i].cbndx == cbndx)
			return true;
	}
	return false;
}

/* Reset may only leave an unclaimed firmware context untouched. */
static inline bool sheng_smmu_boot_context_pinned(
		struct arm_smmu_device *smmu, unsigned int cbndx)
{
	return cbndx < smmu->num_context_banks && !smmu->cbs[cbndx].cfg &&
		sheng_smmu_context_has_pinned_stream(smmu, cbndx);
}

/* EARLY_MAP requests bypass until the display has mapped its splash image.
 * Keep the firmware's bypass memory attributes too, then install the whole
 * Linux context when stage-1 translation is explicitly enabled. */
static inline bool sheng_smmu_defer_boot_context(struct arm_smmu_device *smmu,
		unsigned int cbndx, bool early_map, bool stage1)
{
	return early_map && stage1 &&
		sheng_smmu_context_has_pinned_stream(smmu, cbndx);
}
#endif
