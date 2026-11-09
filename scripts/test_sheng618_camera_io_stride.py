#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile actual stride-selection statements against the captured FD layout."""
import hashlib
import json
import subprocess
from build_sheng618_upstream import CLANG, K618, PROJECT, ROOT

receipt = PROJECT / 'reports/kernel618-camera-io-stride-source.json'
report = json.loads(receipt.read_text())
name = 'vendor/qcom/opensource/camera-kernel/drivers/cam_isp/isp_hw_mgr/isp_hw/vfe_hw/vfe_bus/cam_vfe_bus_ver3.c'
after = (K618 / name).read_text()
before = (ROOT / 'diagnostic/hardware-r37/camera-stride-before' / name.split('camera-kernel/', 1)[1]).read_text()
work = ROOT / 'diagnostic/hardware-r37/camera-stride-check'
work.mkdir(parents=True, exist_ok=True)

def selector(text):
    # Extract the real production statements, up to the register write.
    anchor = '\t\tval = stride;\n\t\tCAM_DBG(CAM_ISP, "VFE:%u io config stride val'
    assert text.count(anchor) == 1
    block = anchor + text.split(anchor, 1)[1]
    block = block.split('\n\t\tCAM_ISP_ADD_REG_VAL_PAIR', 1)[0]
    assert 'val = ALIGNUP(val, 16);' in block and 'val = cfg->stride;' in block
    return block

harness = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <assert.h>
#define ALIGNUP(x,a) (((x)+(a)-1)&~((a)-1))
#define CAM_DBG(...) ((void)0)
struct cfg_t { uint32_t stride; };
struct hw_t { bool use_io_stride; };
struct priv_t { struct hw_t *bus_hw_info; };
static uint32_t select_pitch(uint32_t stride, uint32_t override, bool kalama) {
  struct cfg_t configuration = {override}, *cfg = &configuration;
  struct hw_t hw = {kalama};
  struct priv_t priv = {&hw}, *bus_priv = &priv;
  uint32_t val;
  (void)bus_priv;
  /* PRODUCTION */
  return val;
}
int main(void) {
  unsigned pitch = select_pitch(852, 0, true);
  unsigned end = 409088 + 239 * pitch + 852;
  assert(select_pitch(3328, 0, true) == 3328);
  assert(select_pitch(852, 896, true) == 896);
  assert(select_pitch(852, 0, false) == 864);
  assert(select_pitch(852, 896, false) == 896);
  assert((end > 614400) == EXPECT_OVERFLOW);
  printf("pitch=%u last_UV_write_end=%u allocation=614400 overflow=%u\n",
         pitch, end, end > 614400);
  return 0;
}
'''
results = {}
for label, source, overflow in [('old', before, 1), ('repaired', after, 0)]:
    c = work / (label + '.c')
    c.write_text(harness.replace('/* PRODUCTION */', selector(source)).replace('EXPECT_OVERFLOW', str(overflow)))
    exe = work / label
    subprocess.run([CLANG / 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror', c, '-o', exe], check=True)
    result = subprocess.check_output([exe], text=True).strip()
    results[label] = dict(result=result, compiled_source_sha256=hashlib.sha256(c.read_bytes()).hexdigest(), passed=True)
    print(label + ': ' + result)
vfe = K618 / 'vendor/qcom/opensource/camera-kernel/drivers/cam_isp/isp_hw_mgr/isp_hw/vfe_hw'
enabled = [str(p.relative_to(vfe)) for p in vfe.rglob('*.h') if '.use_io_stride = true,' in p.read_text()]
assert enabled == ['vfe17x/cam_vfe780.h'], enabled
report['host_stride_regression'] = results
report['scope_checked'] = enabled
report['host_check_scope'] = 'Compiled extracted production stride-selection statements and captured buffer bounds; no hardware DMA or video-quality claim'
receipt.write_text(json.dumps(report, indent=2) + '\n')
