#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Keep the firmware's broader SMR while its display stream is still active."""
import difflib
from build_sheng618_upstream import K618, PROJECT, ROOT

tree = K618 / 'soc/drivers/iommu/arm/arm-smmu'
path = tree / 'arm-smmu.c'
before = path.read_text()
text = before
saved = ROOT / 'diagnostic/smmu-smr-source-before.c'
if not saved.exists():
    saved.write_text(before)

def replace(old, new):
    global text
    if new in text:
        return
    assert text.count(old) == 1, old[:100]
    text = text.replace(old, new, 1)

replace('''		if (smrs && smmu->s2crs[idx].count == 0) {
			smrs[idx].id = sid;''', '''		/* count==0 means no Linux owner yet, not that the firmware's
		 * live, pinned match is free. Its mask can cover several display
		 * SIDs (sheng: 0x1c00/0x1c02); narrowing it to this first SID
		 * interrupts the other scanout pipe before DRM has bound. */
		if (smrs && smmu->s2crs[idx].count == 0 &&
		    !sheng_smmu_keep_firmware_smr(smmu, idx)) {
			smrs[idx].id = sid;''')
replace('''	/* It worked! Now, poke the actual hardware */
	for_each_cfg_sme(cfg, fwspec, i, idx)
		arm_smmu_write_sme(smmu, idx);''', '''	/* Claim Linux references without reprogramming an unclaimed firmware
	 * context. A same-CB attach already leaves S2CR unchanged; EARLY_MAP
	 * installs the Linux context once splash buffers have been mapped. */
	for_each_cfg_sme(cfg, fwspec, i, idx) {
		if (sheng_smmu_keep_firmware_smr(smmu, idx) &&
		    sheng_smmu_boot_context_pinned(smmu, smmu->s2crs[idx].cbndx)) {
			dev_info(smmu->dev,
				"sheng splash: retain SMR%d id=%x mask=%x CB%u at claim\\n",
				idx, smrs[idx].id, smrs[idx].mask,
				smmu->s2crs[idx].cbndx);
			continue;
		}
		arm_smmu_write_sme(smmu, idx);
	}''')
replace('''				smmu->s2crs[i].pinned = true;
				bitmap_set(smmu->context_map, smmu->s2crs[i].cbndx, 1);''', '''				smmu->s2crs[i].pinned = true;
				dev_info(smmu->dev,
					"sheng splash: handoff SMR%u raw=%x S2CR=%x id=%x mask=%x CB%u\\n",
					i, smr, s2cr, smrs.id, smrs.mask,
					smmu->s2crs[i].cbndx);
				bitmap_set(smmu->context_map, smmu->s2crs[i].cbndx, 1);''')
if text != before:
    (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-smmu-smr-handoff.patch').write_text(
        ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
            fromfile='a/soc/drivers/iommu/arm/arm-smmu/arm-smmu.c',
            tofile='b/soc/drivers/iommu/arm/arm-smmu/arm-smmu.c')))
    path.write_text(text)
(tree / 'sheng_smmu_handoff.h').write_bytes(
    (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng_smmu_handoff.h').read_bytes())
print('Firmware SMR mask retained at allocation; unclaimed firmware registers untouched')
