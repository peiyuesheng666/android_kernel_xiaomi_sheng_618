#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the production handoff policy with distinct SMR and CB indices."""
from pathlib import Path
import subprocess
import tempfile

header = Path(__file__).resolve().parents[1] / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng_smmu_handoff.h'
source = '''#include <stdbool.h>
#include <assert.h>
#include <stddef.h>
enum { S2CR_TYPE_TRANS, S2CR_TYPE_BYPASS, S2CR_TYPE_FAULT };
#define ARM_SMMU_SCTLR_M 1U
#define ARM_SMMU_CB_SCTLR 0U
struct arm_smmu_s2cr { bool pinned; int type; unsigned int cbndx; };
struct arm_smmu_cb { void *cfg; unsigned int sctlr, hardware_sctlr; };
struct arm_smmu_device { unsigned int num_context_banks, num_mapping_groups;
 struct arm_smmu_s2cr *s2crs; struct arm_smmu_cb *cbs; };
static unsigned int arm_smmu_cb_read(struct arm_smmu_device *s,
 unsigned int cb, unsigned int reg) {
 assert(reg == ARM_SMMU_CB_SCTLR); return s->cbs[cb].hardware_sctlr;
}
''' + header.read_text() + '''
int main(void) {
 struct arm_smmu_s2cr streams[12] = {0};
 struct arm_smmu_cb contexts[4] = {0};
 struct arm_smmu_device smmu = {4, 12, streams, contexts};
 streams[9] = (struct arm_smmu_s2cr){true, S2CR_TYPE_TRANS, 2};
 assert(sheng_smmu_firmware_bypass_active(&smmu));
 assert(sheng_smmu_boot_context_pinned(&smmu, 2));
 assert(!sheng_smmu_boot_context_pinned(&smmu, 0));
 assert(!sheng_smmu_boot_context_pinned(&smmu, 3));
 assert(!sheng_smmu_boot_context_pinned(&smmu, 4));
 contexts[2].cfg = &smmu;
 assert(sheng_smmu_firmware_bypass_active(&smmu));
 contexts[2].sctlr = ARM_SMMU_SCTLR_M;
 assert(sheng_smmu_firmware_bypass_active(&smmu));
 contexts[2].hardware_sctlr = ARM_SMMU_SCTLR_M;
 assert(!sheng_smmu_firmware_bypass_active(&smmu));
 streams[10] = (struct arm_smmu_s2cr){true, S2CR_TYPE_TRANS, 1};
 assert(sheng_smmu_firmware_bypass_active(&smmu));
 contexts[1].cfg = &smmu;
 assert(sheng_smmu_firmware_bypass_active(&smmu));
 contexts[1].sctlr = ARM_SMMU_SCTLR_M;
 assert(sheng_smmu_firmware_bypass_active(&smmu));
 contexts[1].hardware_sctlr = ARM_SMMU_SCTLR_M;
 assert(!sheng_smmu_firmware_bypass_active(&smmu));
 streams[10].pinned = false;
 assert(!sheng_smmu_boot_context_pinned(&smmu, 2));
 assert(sheng_smmu_context_has_pinned_stream(&smmu, 2));
 assert(sheng_smmu_defer_boot_context(&smmu, 2, true, true));
 assert(!sheng_smmu_defer_boot_context(&smmu, 2, false, true));
 assert(!sheng_smmu_defer_boot_context(&smmu, 2, true, false));
 assert(!sheng_smmu_defer_boot_context(&smmu, 4, true, true));
 contexts[2].cfg = NULL;
 streams[9].pinned = false;
 assert(!sheng_smmu_boot_context_pinned(&smmu, 2));
 assert(!sheng_smmu_defer_boot_context(&smmu, 2, true, true));
 streams[9].pinned = true;
 streams[9].type = S2CR_TYPE_BYPASS;
 assert(!sheng_smmu_boot_context_pinned(&smmu, 2));
 assert(!sheng_smmu_defer_boot_context(&smmu, 2, true, true));
 streams[9].type = S2CR_TYPE_FAULT;
 assert(!sheng_smmu_boot_context_pinned(&smmu, 2));
 assert(!sheng_smmu_firmware_bypass_active(&smmu));
 streams[9] = (struct arm_smmu_s2cr){true, S2CR_TYPE_TRANS, 4};
 assert(!sheng_smmu_firmware_bypass_active(&smmu));
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='sheng-smmu-test-') as temporary:
    folder = Path(temporary)
    (folder / 'test.c').write_text(source)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
        str(folder / 'test.c'), '-o', str(folder / 'test')], check=True)
    subprocess.run([folder / 'test'], check=True)
print('Production policy passed: distinct indices, pending EARLY_MAP, all pinned contexts live, bypass/fault and bounds')
