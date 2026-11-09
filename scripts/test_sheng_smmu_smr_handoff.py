#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run old/new production SMR allocation against sheng's dual-display SID range."""
from pathlib import Path
import subprocess
import tempfile
from build_sheng618_upstream import K618, PROJECT, ROOT

def functions(text):
    first = text.index('static int arm_smmu_find_sme(')
    last = text.index('static bool arm_smmu_free_sme(', first)
    alloc = text.index('static int arm_smmu_master_alloc_smes(')
    end = text.index('static void arm_smmu_master_free_smes(', alloc)
    return text[first:last] + text[alloc:end]

preamble = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
typedef uint16_t u16;
typedef int16_t s16;
typedef uint8_t u8;
#define ARM_SMMU_SMR_ID 0xffffU
#define ARM_SMMU_SMR_MASK 0x7fff0000U
#define FIELD_GET(m,v) (((v)&(m)) >> __builtin_ctz(m))
#define INVALID_SMENDX (-1)
#define WARN_ON(x) (!!(x))
#define dev_info(...) ((void)0)
#define mutex_lock(p) ((void)(p))
#define mutex_unlock(p) ((void)(p))
#define S2CR_TYPE_TRANS 0
#define ARM_SMMU_SCTLR_M 1U
#define ARM_SMMU_CB_SCTLR 0U
struct arm_smmu_smr { unsigned int id, mask; bool valid, used; };
struct arm_smmu_s2cr { unsigned int count, type, cbndx; bool pinned; };
struct arm_smmu_cb { void *cfg; unsigned int sctlr; };
struct arm_smmu_device {
    unsigned int num_mapping_groups, num_context_banks;
    struct arm_smmu_smr *smrs;
    struct arm_smmu_s2cr *s2crs;
    struct arm_smmu_cb *cbs;
    int stream_map_mutex, dev;
};
static unsigned int arm_smmu_cb_read(struct arm_smmu_device *s,
    unsigned int cb, unsigned int reg) {
    (void)reg; return s->cbs[cb].sctlr;
}
struct iommu_fwspec { int num_ids; unsigned int ids[2]; };
struct arm_smmu_master_cfg { struct arm_smmu_device *smmu; s16 smendx[2]; };
struct device { struct iommu_fwspec f; struct arm_smmu_master_cfg c; bool defer; };
#define dev_iommu_fwspec_get(d) (&(d)->f)
#define dev_iommu_priv_get(d) (&(d)->c)
#define for_each_cfg_sme(c,f,i,x) \
    for ((i)=0; (i)<(f)->num_ids && (((x)=(c)->smendx[i]),1); (i)++)
static bool dev_defer_smr_configuration(struct device *d) { return d->defer; }
static int writes;
static void arm_smmu_write_sme(struct arm_smmu_device *s, int i) {
    (void)s; (void)i; writes++;
}
static bool arm_smmu_free_sme(struct arm_smmu_device *s, int i) {
    assert(s->s2crs[i].count); s->s2crs[i].count--; return false;
}
'''
harness = r'''
int main(void) {
    struct arm_smmu_smr smrs[3] = {{.id=0x1c00,.mask=2,.valid=true,.used=true}};
    struct arm_smmu_s2cr s2crs[3] = {{.type=S2CR_TYPE_TRANS,.pinned=true,.cbndx=3}};
    struct arm_smmu_cb cbs[4] = {{0}};
    struct arm_smmu_device s = {.num_mapping_groups=3,.num_context_banks=4,
        .smrs=smrs,.s2crs=s2crs,.cbs=cbs};
    struct device first = {.f={.num_ids=1,.ids={0x1c00}},
        .c={.smmu=&s,.smendx={-1,-1}}};
    assert(arm_smmu_master_alloc_smes(&first) == 0);
    assert(first.c.smendx[0] == 0 && s2crs[0].count == 1);
#if EXPECT_FIXED
    assert(smrs[0].id == 0x1c00 && smrs[0].mask == 2 && writes == 0);
    assert(arm_smmu_find_sme(&s, 0x1c02, 0) == 0);
    struct device second = {.f={.num_ids=1,.ids={0x1c02}},
        .c={.smmu=&s,.smendx={-1,-1}}};
    assert(arm_smmu_master_alloc_smes(&second) == 0);
    assert(second.c.smendx[0] == 0 && s2crs[0].count == 2 && writes == 0);
    struct device ordinary = {.f={.num_ids=1,.ids={0x2e00}},
        .c={.smmu=&s,.smendx={-1,-1}}};
    assert(arm_smmu_master_alloc_smes(&ordinary) == 0);
    assert(ordinary.c.smendx[0] == 1 && smrs[1].id == 0x2e00 && writes == 1);
    struct device invalid = {.f={.num_ids=1,.ids={0x1c00}},.defer=true,
        .c={.smmu=&s,.smendx={-1,-1}}};
    assert(arm_smmu_master_alloc_smes(&invalid) == -EINVAL);
    assert(invalid.c.smendx[0] == -1 && s2crs[0].count == 2 && writes == 1);
    assert(!sheng_smmu_keep_firmware_smr(&s, 3));
#else
    assert(smrs[0].mask == 0 && writes == 1);
    assert(arm_smmu_find_sme(&s, 0x1c02, 0) != 0);
#endif
    return 0;
}
'''
header = (PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng_smmu_handoff.h').read_text()
sources = [ROOT / 'diagnostic/smmu-smr-source-before.c',
           K618 / 'soc/drivers/iommu/arm/arm-smmu/arm-smmu.c']
with tempfile.TemporaryDirectory(prefix='sheng-smmu-smr-') as directory:
    root = Path(directory)
    for fixed, source in enumerate(sources):
        path = root / f'alloc{fixed}.c'
        path.write_text(preamble + header + functions(source.read_text()) + harness)
        binary = root / f'alloc{fixed}'
        subprocess.run(['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-Wno-sign-compare', '-fsanitize=address,undefined',
            f'-DEXPECT_FIXED={fixed}', str(path), '-o', str(binary)], check=True)
        subprocess.run([binary], check=True)
print('Production old/new allocation: old drops 1c02; new retains both display SIDs, ordinary mapping and error rollback passed')
