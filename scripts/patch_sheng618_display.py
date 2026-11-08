#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restore sheng's DT-driven video timing selection in the selected display tree.

Reference: MiCode sheng display 6461221b68908b990e1fa2b60feaa812cb944ef5,
dsi_panel_get_mode_count and dsi_display_get_modes_helper. Keep the existing
6.18 driver; only handle mi,video-mode-multi-timing and its per-timing FPS list.
"""
import difflib
import hashlib
import json
from pathlib import Path

from build_sheng618_upstream import K618, PROJECT

tree = K618 / 'vendor/qcom/opensource/display-drivers'
receipt = PROJECT / 'reports/kernel618-display-multitiming-source.json'
patch = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/display-multitiming.patch'


def sha(data):
    return hashlib.sha256(data).hexdigest()


changes = {
    'msm/dsi/dsi_defs.h': [(
        '\tu32 allowed_mode_switch;\n',
        '\t/* k618 sheng: immutable parser-owned per-timing FPS cells. */\n'
        '\tconst __be32 *k618_mi_fps;\n\tu32 k618_mi_fps_count;\n'
        '\tu32 allowed_mode_switch;\n')],
    'msm/dsi/dsi_panel.c': [(
        '\t\t!panel->panel_mode_switch_enabled)\n\t\tcount = SINGLE_MODE_SUPPORT;',
        '\t\t!panel->panel_mode_switch_enabled &&\n'
        '\t\t!utils->read_bool(utils->data, "mi,video-mode-multi-timing"))\n'
        '\t\tcount = SINGLE_MODE_SUPPORT;'), (
        '\tnum_video_modes = num_video_modes * num_dfps_rates;',
        '\t/* MiCode sheng: timings partition the global FPS list. */\n'
        '\tif (panel->dfps_caps.dfps_support &&\n'
        '\t    utils->read_bool(utils->data, "mi,video-mode-multi-timing"))\n'
        '\t\tnum_video_modes = 1;\n\n'
        '\tnum_video_modes = num_video_modes * num_dfps_rates;'), (
        '\t\trc = dsi_panel_parse_timing(&mode->timing, utils);',
        '\t\t/* The parser backing data lives as long as the panel. */\n'
        '\t\tif (utils->read_bool(utils_data, "mi,video-mode-multi-timing")) {\n'
        '\t\t\tint bytes = 0;\n\n'
        '\t\t\tprv_info->k618_mi_fps = utils->get_property(utils->data,\n'
        '\t\t\t\t\t"mi,mdss-dsi-supported-fps-list", &bytes);\n'
        '\t\t\tif (!prv_info->k618_mi_fps || bytes <= 0 ||\n'
        '\t\t\t    bytes % sizeof(__be32)) {\n'
        '\t\t\t\tDSI_ERR("missing/invalid sheng timing FPS list %u\\n", index);\n'
        '\t\t\t\trc = -EINVAL;\n\t\t\t\tgoto parse_fail;\n\t\t\t}\n'
        '\t\t\tprv_info->k618_mi_fps_count = bytes / sizeof(__be32);\n\t\t}\n\n'
        '\t\trc = dsi_panel_parse_timing(&mode->timing, utils);')],
    'msm/dsi/dsi_display.c': [(
        '\t\t\tstruct dsi_display_mode *sub_mode =\n'
        '\t\t\t\t\t&display->modes[array_idx];\n\t\t\tu32 curr_refresh_rate;',
        '\t\t\tstruct dsi_display_mode *sub_mode;\n\t\t\tu32 curr_refresh_rate;\n'
        '\t\t\tu32 j;\n\t\t\tbool supported = false;\n\n'
        '\t\t\t/* k618 sheng: use only rates belonging to this timing. */\n'
        '\t\t\tif (dfps_caps.dfps_support && support_video_mode &&\n'
        '\t\t\t    display_mode.priv_info->k618_mi_fps_count) {\n'
        '\t\t\t\tfor (j = 0; j < display_mode.priv_info->k618_mi_fps_count; j++)\n'
        '\t\t\t\t\tif (be32_to_cpup(&display_mode.priv_info->k618_mi_fps[j]) ==\n'
        '\t\t\t\t\t    dfps_caps.dfps_list[i])\n'
        '\t\t\t\t\t\tsupported = true;\n'
        '\t\t\t\tif (!supported)\n\t\t\t\t\tcontinue;\n\t\t\t}\n'
        '\t\t\tif (array_idx >= display->panel->num_display_modes)\n'
        '\t\t\t\treturn -EOVERFLOW;\n'
        '\t\t\tsub_mode = &display->modes[array_idx];'), (
        '\tif (dsc_modes && nondsc_modes)\n\t\tdisplay->panel->dsc_switch_supported = true;',
        '\tif (array_idx != display->panel->num_display_modes) {\n'
        '\t\tDSI_ERR("mode table incomplete: %u/%u\\n", array_idx,\n'
        '\t\t\tdisplay->panel->num_display_modes);\n\t\treturn -EINVAL;\n\t}\n'
        '\tDSI_INFO("k618 mode table: %u modes from %u timings\\n",\n'
        '\t\tarray_idx, timing_mode_count);\n\n'
        '\tif (dsc_modes && nondsc_modes)\n\t\tdisplay->panel->dsc_switch_supported = true;'), (
        '\tif (rc)\n\t\tkfree(display->modes);',
        '\tif (rc) {\n\t\tkfree(display->modes);\n\t\tdisplay->modes = NULL;\n\t}')],
}

already_applied = False
if receipt.is_file():
    previous = json.loads(receipt.read_text())
    if all(sha((tree / p).read_bytes()) == hashes['after']
           for p, hashes in previous['files'].items()):
        already_applied = True

files, diff = {}, []
prepared = {}
for relative, replacements in changes.items():
    before = (tree / relative).read_text()
    if already_applied:
        # Recover the exact preimage for a reproducible patch receipt, without
        # rewriting or rebuilding the already-patched source.
        for old, new in reversed(replacements):
            assert before.count(new) == 1, relative
            before = before.replace(new, old, 1)
    after = before
    for old, new in replacements:
        assert after.count(old) == 1, (relative, old[:100], after.count(old))
        after = after.replace(old, new, 1)
    prepared[relative] = after
    files[relative] = {'before': sha(before.encode()), 'after': sha(after.encode())}
    diff.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                     fromfile='a/' + relative, tofile='b/' + relative, n=0))

# Validate all replacement anchors before changing any file.
if not already_applied:
    for relative, after in prepared.items():
        (tree / relative).write_text(after)
patch.write_text(''.join(diff))
result = {'reference_repository': 'https://github.com/MiCode/vendor_opensource_display-drivers',
          'reference_revision': '6461221b68908b990e1fa2b60feaa812cb944ef5',
          'los_comparison_revision': '92a9fde479d3262da080cfd28bab0775b0da500a',
          'files': files, 'patch': str(patch.relative_to(PROJECT)),
          'patch_sha256': sha(patch.read_bytes()), 'source_tree': str(tree),
          'new_hardware_parameters': False,
          'scope': 'MiCode DT multi-timing selection and complete mode table validation',
          'hardware_result': 'pending'}
receipt.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
