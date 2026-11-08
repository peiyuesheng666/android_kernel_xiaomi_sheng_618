#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Execute real DSC math from MiCode and candidate; compare full configuration bytes."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from build_sheng618_upstream import ACK, K618, PROJECT, ROOT

native = ROOT / 'diagnostic/panel-r19/dsc-test'
native.mkdir(parents=True, exist_ok=True)
header = (ACK / 'include/drm/display/drm_dsc.h').read_text()
structs = '\n'.join(re.search(r'struct ' + name + r' \{.*?\n\};', header, re.S)[0]
                    for name in ('drm_dsc_rc_range_parameters', 'drm_dsc_config'))
constants = '\n'.join(line for line in header.splitlines() if line.startswith('#define DSC_'))
common = '''#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define DIV_ROUND_UP(a,b) (((a)+(b)-1)/(b))
#define DSC_BPP(c) ((c).bits_per_pixel >> 4)
#define SDE_ERROR(...) ((void)0)
#define SDE_INFO(...) ((void)0)
#define MSM_CHROMA_444 0
#define MSM_CHROMA_422 1
#define MSM_CHROMA_420 2
''' + constants + '\n' + structs + '\n'
panel_ids = (ROOT / 'src/micode-display/msm/mi_disp/mi_panel_id.h').read_text()
legacy_ids = '\n'.join(line for line in panel_ids.splitlines() if line.startswith('#define ') and '_PANEL_ID ' in line)
for function in ('is_use_nvt_dsc_config', 'is_use_nt37705_dsc_config'):
    legacy_ids += '\n' + re.search(r'static inline bool ' + function + r'\(.*?\n\}', panel_ids, re.S)[0]
sources = {
    'micode': ROOT / 'src/micode-display/msm/sde_dsc_helper.c',
    'candidate': K618 / 'vendor/qcom/opensource/display-drivers/msm/sde_dsc_helper.c',
}
digests = {}
for label, path in sources.items():
    text = path.read_text()
    digests[label] = hashlib.sha256(path.read_bytes()).hexdigest()
    body = text[text.index('enum sde_dsc_ratio_type'):text.index('int sde_dsc_populate_dsc_private_params(')]
    entry = 'sde_dsc_populate_dsc_config' + ('_with_panel' if label == 'candidate' else '')
    main = '''
int main(void) {
    for (int scr=0; scr<2; scr++) {
        struct drm_dsc_config c = {0};
        c.dsc_version_major=1; c.dsc_version_minor=1;
        c.pic_width=1524; c.pic_height=2032;
        c.slice_width=762; c.slice_height=16; c.slice_count=2;
        c.bits_per_component=8; c.bits_per_pixel=8<<4;
        c.block_pred_enable=1;
        if (ENTRY(&c,scr,0x4e38316150360200ULL)) return 1;
        fwrite(&c,sizeof(c),1,stdout);
        fprintf(stderr,"scr=%d first_line=%u dec_delay=%u nfl_bpg=%u scale_inc=%u\\n",
            scr,c.first_line_bpg_offset,c.initial_dec_delay,c.nfl_bpg_offset,c.scale_increment_interval);
    }
    return 0;
}
'''.replace('ENTRY', entry)
    generated = native / (label + '.c')
    generated.write_text(common + (legacy_ids if label == 'micode' else '') + '\n' + body + main)
    subprocess.run(['gcc', '-std=gnu11', '-O2', '-Wall', str(generated), '-o', str(native / label)], check=True)
    result = subprocess.run([str(native / label)], capture_output=True, check=True)
    (native / (label + '.bin')).write_bytes(result.stdout)
    (native / (label + '.txt')).write_bytes(result.stderr)
    print(label + ': ' + result.stderr.decode(), flush=True)
assert (native / 'micode.bin').read_bytes() == (native / 'candidate.bin').read_bytes(), 'DSC configs differ'
report = dict(actual_c_helpers_executed=True, full_drm_dsc_config_bytes_match=True,
              sources_sha256=digests, modes=dict(width_per_dsi=1524, height=2032,
              slice_width=762, slice_height=16, bpc=8, bpp=8, dsc_version='1.1'),
              scr_revisions_tested=[0, 1], hardware_scanout_tested=False,
              candidate_results=(native / 'candidate.txt').read_text())
(PROJECT / 'reports/kernel618-panel-r19-dsc-math.json').write_text(json.dumps(report, indent=2)+'\n')
