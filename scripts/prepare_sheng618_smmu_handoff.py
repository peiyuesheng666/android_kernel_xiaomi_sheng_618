#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Keep the DT-pinned boot scanout translation running during SMMU probe."""
import difflib
from build_sheng618_upstream import K618, PROJECT

folder = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18'
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

replace('#include "arm-smmu.h"\n',
    '#include "arm-smmu.h"\n#include "sheng_smmu_handoff.h"\n')
replace('''		for (i = 0; i < smmu->num_mapping_groups; ++i)
			arm_smmu_write_sme(smmu, i);
''', '''		for (i = 0; i < smmu->num_mapping_groups; ++i) {
			/* Leave the live firmware SMR/S2CR pair untouched. */
			if (smmu->s2crs[i].pinned &&
			    smmu->s2crs[i].type == S2CR_TYPE_TRANS &&
			    sheng_smmu_boot_context_pinned(smmu, smmu->s2crs[i].cbndx))
				continue;
			arm_smmu_write_sme(smmu, i);
		}
''')
replace('''		for (i = 0; i < smmu->num_context_banks; ++i) {
			arm_smmu_write_context_bank(smmu, i);
			arm_smmu_cb_write(smmu, i, ARM_SMMU_CB_FSR, ARM_SMMU_CB_FSR_FAULT);
		}
''', '''		for (i = 0; i < smmu->num_context_banks; ++i) {
			if (sheng_smmu_boot_context_pinned(smmu, i)) {
				dev_info(dev, "sheng splash: preserve firmware CB%d SCTLR=%x\\n",
					i, arm_smmu_cb_read(smmu, i, ARM_SMMU_CB_SCTLR));
				continue;
			}
			arm_smmu_write_context_bank(smmu, i);
			arm_smmu_cb_write(smmu, i, ARM_SMMU_CB_FSR, ARM_SMMU_CB_FSR_FAULT);
		}
''')
replace('''	iort_get_rmr_sids(dev_fwnode(smmu->dev), &rmr_list);

	/*
''', '''	iort_get_rmr_sids(dev_fwnode(smmu->dev), &rmr_list);

	/* A DT system has no ACPI RMRs. CLIENTPD would interrupt the pinned
	 * display even though this function has no mappings to install. */
	if (list_empty(&rmr_list)) {
		iort_put_rmr_sids(dev_fwnode(smmu->dev), &rmr_list);
		dev_info(smmu->dev, "sheng splash: empty RMR list; client access retained\\n");
		return;
	}

	/*
''')
patch = ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
    fromfile='a/' + str(path.relative_to(K618)), tofile='b/' + str(path.relative_to(K618))))
if patch:
    (folder / 'sheng-smmu-handoff.patch').write_text(patch)
(tree / 'sheng_smmu_handoff.h').write_bytes((folder / 'sheng_smmu_handoff.h').read_bytes())
path.write_text(text)
print('Pinned firmware stream/context preserved; empty ACPI RMR no longer stops clients')
