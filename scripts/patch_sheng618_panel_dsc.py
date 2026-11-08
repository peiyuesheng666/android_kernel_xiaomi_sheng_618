#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restore the MiCode N81A DSC first-line offset before derived rate-control math."""
import difflib
import hashlib
import json
from build_sheng618_upstream import K618, PROJECT

tree = K618 / 'vendor/qcom/opensource/display-drivers'
receipt = PROJECT / 'reports/kernel618-panel-dsc-source.json'
changes = {
    'msm/sde_dsc_helper.h': [
        ('int sde_dsc_populate_dsc_config(struct drm_dsc_config *dsc, int scr_ver);',
         'int sde_dsc_populate_dsc_config(struct drm_dsc_config *dsc, int scr_ver);\n'
         'int sde_dsc_populate_dsc_config_with_panel(struct drm_dsc_config *dsc,\n'
         '\t\tint scr_ver, u64 panel_id);'),
    ],
    'msm/sde_dsc_helper.c': [
        ('int sde_dsc_populate_dsc_config(struct drm_dsc_config *dsc, int scr_ver) {',
         'int sde_dsc_populate_dsc_config_with_panel(struct drm_dsc_config *dsc,\n'
         '\t\tint scr_ver, u64 panel_id) {'),
        ('\t\t\tdsc->first_line_bpg_offset = 12;\n',
         '\t\t\tdsc->first_line_bpg_offset = 12;\n'
         '\t\t/* MiCode sheng: NT37705 needs 13, including derived RC fields. */\n'
         '\t\tif (panel_id == 0x4e38316150360200ULL)\n'
         '\t\t\tdsc->first_line_bpg_offset = 13;\n'),
        ('int sde_dsc_populate_dsc_private_params(',
         'int sde_dsc_populate_dsc_config(struct drm_dsc_config *dsc, int scr_ver)\n'
         '{\n\treturn sde_dsc_populate_dsc_config_with_panel(dsc, scr_ver, 0);\n}\n\n'
         'int sde_dsc_populate_dsc_private_params('),
    ],
    'msm/dsi/dsi_panel.c': [
        ('static int dsi_panel_parse_dsc_params(struct dsi_display_mode *mode,',
         'static int dsi_panel_parse_dsc_params(struct dsi_panel *panel, struct dsi_display_mode *mode,'),
        ('\trc = sde_dsc_populate_dsc_config(&priv_info->dsc.config,\n'
         '\t\t\tpriv_info->dsc.scr_rev);',
         '\t{\n\t\tu64 panel_id = 0;\n\n'
         '\t\tof_property_read_u64(panel->panel_of_node, "mi,panel-id", &panel_id);\n'
         '\t\trc = sde_dsc_populate_dsc_config_with_panel(&priv_info->dsc.config,\n'
         '\t\t\t\tpriv_info->dsc.scr_rev, panel_id);\n'
         '\t\tif (!rc && panel_id == 0x4e38316150360200ULL)\n'
         '\t\t\tDSI_INFO("sheng DSC: first_line=%u dec_delay=%u nfl_bpg=%u scale_inc=%u\\n",\n'
         '\t\t\t\tpriv_info->dsc.config.first_line_bpg_offset,\n'
         '\t\t\t\tpriv_info->dsc.config.initial_dec_delay,\n'
         '\t\t\t\tpriv_info->dsc.config.nfl_bpg_offset,\n'
         '\t\t\t\tpriv_info->dsc.config.scale_increment_interval);\n\t}'),
        ('rc = dsi_panel_parse_dsc_params(mode, utils);',
         'rc = dsi_panel_parse_dsc_params(panel, mode, utils);'),
    ],
}
previous = json.loads(receipt.read_text()) if receipt.exists() else None
prepared, hashes, patch = {}, {}, []
for name, replacements in changes.items():
    before = (tree / name).read_text()
    if previous and hashlib.sha256(before.encode()).hexdigest() == previous['files'][name]['after']:
        for old, new in reversed(replacements):
            assert before.count(new) == 1, name
            before = before.replace(new, old, 1)
    after = before
    for old, new in replacements:
        assert after.count(old) == 1, (name, old[:100])
        after = after.replace(old, new, 1)
    prepared[name] = after
    hashes[name] = dict(before=hashlib.sha256(before.encode()).hexdigest(),
                        after=hashlib.sha256(after.encode()).hexdigest())
    patch.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                 fromfile='a/' + name, tofile='b/' + name, n=0))
for name, text in prepared.items():
    (tree / name).write_text(text)
(PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/panel-dsc.patch').write_text(''.join(patch))
receipt.write_text(json.dumps(dict(
    reference_repository='https://github.com/MiCode/vendor_opensource_display-drivers',
    reference_revision='6461221b68908b990e1fa2b60feaa812cb944ef5',
    reference_functions=['sde_dsc_populate_dsc_config', 'is_use_nt37705_dsc_config'],
    panel_id='0x4e38316150360200', live_dtb='diagnostic/disklog-r5/live.dts',
    observed_difference='DSC 1.1 first_line_bpg_offset 12 -> stock NT37705 13 before derived RC calculations',
    generic_dsi_and_dp_entry_preserved=True, files=hashes,
    hardware_result='pending', screen_corruption_fixed_claimed=False), indent=2) + '\n')
print('N81A DSC patch applied', flush=True)
