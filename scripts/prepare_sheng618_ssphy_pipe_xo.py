#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Use the actual GCC XO mux parent for sheng's QMP suspend path."""
import difflib
import hashlib
import json
from pathlib import Path

from build_sheng618_upstream import K618, PROJECT, ROOT

relative = 'drivers/usb/phy/phy-msm-ssusb-qmp.c'
path = K618 / 'soc' / relative
gcc = K618 / 'soc/drivers/clk/qcom/gcc-kalama.c'
live = ROOT / 'diagnostic/disklog-r5/live.dts'
assert 'model = "Qualcomm Technologies, Inc. 8550 sheng";' in live.read_text()
assert '''static const struct clk_parent_data gcc_parent_data_13[] = {
\t{ .fw_name = "usb3_phy_wrapper_gcc_usb30_pipe_clk" },
\t{ .fw_name = "bi_tcxo" },
};''' in gcc.read_text()

helper = '''/* sheng's PHY ref_clk_src is XO_PAD, not a parent of the GCC pipe mux.
 * Keep that reference vote, but select the GCC mux's own bi_tcxo on suspend.
 * Parent index 1 belongs to the fixed gcc-kalama parent_data_13, not a
 * hardware selector value. Do not alter other boards or clock topologies.
 */
static int sheng_ssphy_qmp_get_pipe_xo(struct msm_ssphy_qmp *phy,
\t\tstruct device *dev)
{
\tstruct clk_hw *mux, *xo;

\tphy->pipe_clk_xo = phy->ref_clk_src;
\tif (!of_root || of_property_match_string(of_root, "model",
\t\t\t"Qualcomm Technologies, Inc. 8550 sheng") < 0 ||
\t\t\t!phy->pipe_clk_mux || !phy->ref_clk_src)
\t\treturn 0;

\tmux = __clk_get_hw(phy->pipe_clk_mux);
\tif (!mux || strcmp(clk_hw_get_name(mux),
\t\t\t"gcc_usb3_prim_phy_pipe_clk_src"))
\t\treturn 0;
\tif (clk_has_parent(phy->pipe_clk_mux, phy->ref_clk_src))
\t\treturn 0;
\tif (clk_hw_get_num_parents(mux) != 2)
\t\treturn dev_err_probe(dev, -EINVAL, "unexpected sheng pipe mux parents\\n");

\txo = clk_hw_get_parent_by_index(mux, 1);
\tif (!xo)
\t\treturn dev_err_probe(dev, -EPROBE_DEFER, "GCC pipe XO parent not ready\\n");
\tphy->pipe_clk_xo = devm_clk_hw_get_clk(dev, xo, "pipe_clk_xo");
\tif (IS_ERR(phy->pipe_clk_xo))
\t\treturn dev_err_probe(dev, PTR_ERR(phy->pipe_clk_xo),
\t\t\t\t"failed to get GCC pipe XO parent\\n");
\tdev_info(dev, "sheng pipe suspend parent: %s\\n", clk_hw_get_name(xo));
\treturn 0;
}

'''
changes = [
    ('#include <linux/clk.h>\n', '#include <linux/clk.h>\n#include <linux/clk-provider.h>\n'),
    ('\tstruct clk\t\t*pipe_clk_mux;\n', '\tstruct clk\t\t*pipe_clk_mux;\n\tstruct clk\t\t*pipe_clk_xo;\n'),
    ('static int msm_ssphy_qmp_get_clks(struct msm_ssphy_qmp *phy, struct device *dev)\n',
     helper + 'static int msm_ssphy_qmp_get_clks(struct msm_ssphy_qmp *phy, struct device *dev)\n'),
    ('\nerr:\n\treturn ret;\n}\n\nstatic void msm_ssphy_qmp_enable_clks',
     '\n\tret = sheng_ssphy_qmp_get_pipe_xo(phy, dev);\n\nerr:\n\treturn ret;\n}\n\nstatic void msm_ssphy_qmp_enable_clks'),
    ('clk_set_parent(phy->pipe_clk_mux, phy->ref_clk_src);',
     'clk_set_parent(phy->pipe_clk_mux, phy->pipe_clk_xo);'),
]
text = path.read_text()
before = text
for old, new in changes:
    if new in text:
        assert text.count(new) == 1
    else:
        assert text.count(old) == 1, old
        text = text.replace(old, new, 1)
for old, new in reversed(changes):
    before = before.replace(new, old, 1)
path.write_text(text)
folder = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18'
patch = folder / 'ssphy-pipe-xo.patch'
patch.write_text(''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
                                           fromfile='a/' + relative, tofile='b/' + relative)))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
report = dict(revision='hardware-r37', date='2026-11-09', source=relative,
              before_sha256=hashlib.sha256(before.encode()).hexdigest(), after_sha256=sha(path),
              patch_sha256=sha(patch), gcc_source_sha256=sha(gcc), live_dt_sha256=sha(live),
              scope='Exact shipping sheng model and GCC primary pipe mux; compatible legacy fallback elsewhere',
              defect='SS PHY ref_clk_src is RPMH_CXO_PAD_CLK, but GCC pipe mux accepts PHY pipe or bi_tcxo',
              change='Retain PHY reference clock voting; use a managed handle to actual GCC parent index 1 for suspend',
              probe_defer_preserved_for_unresolved_gcc_parent=True,
              board_dt_changed=False, root_components_added=False,
              evidence='r35 current-kernel.txt: pipe_clk set_parent disable failed; fixed source parent matrix and shipping DT',
              references=[
                  dict(repository='selected-soc-provider', commit='b1916e6fb00018222d54469e507a729e5e9291bf'),
                  dict(repository='LineageOS-sm8550-nuwa', commit='f9ca2b71f6725a0d4f0b1cb2aa553baaea98e74d',
                       applicability='Same GCC parent matrix; legacy QMP driver also selects ref_clk_src, so it does not repair this CCF identity mismatch'),
                  dict(repository='MiCode-sheng', commit='29db5d592c5b577aa9d9611da988a5e071d100dd',
                       applicability='Reference voting preserved; legacy driver made the same parent selection without checking its failure'),
                  dict(repository='LineageOS-piano', commit='3f10fc25273b42d18d0bd533551a0a5c3dda0094',
                       applicability='Different Qualcomm platform; its board values do not apply to Kalama GCC'),
                  dict(repository='ACK', commit='ff4a6c3bb0f471a9dd186293a47b62c83829b97d',
                       applicability='clk_has_parent/clk_hw_get_parent_by_index/devm_clk_hw_get_clk exported CCF interfaces')],
              build_result='pending', hardware_result='pending', usb_fixed=False,
              limitation='Repairs a proven clock-parent contract error; its role in total USB/no-charging remains to be tested')
(PROJECT / 'reports/kernel618-ssphy-pipe-xo-source.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
