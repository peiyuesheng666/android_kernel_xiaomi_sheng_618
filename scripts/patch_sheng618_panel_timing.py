#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restore the stock N81A video-rate command sequence, using this device's DT."""
import difflib
import hashlib
import json
import sys
from build_sheng618_upstream import K618, PROJECT, ROOT

tree = K618 / 'vendor/qcom/opensource/display-drivers'
reference = ROOT / 'src/micode-display'
receipt = PROJECT / 'reports/kernel618-panel-timing-source.json'
patch = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/panel-timing.patch'
if receipt.exists():
    prior = json.loads(receipt.read_text())
    if all(hashlib.sha256((tree/name).read_bytes()).hexdigest() == hashes['after']
           for name, hashes in prior['files'].items()):
        print('N81A video timing sequence already applied', flush=True)
        sys.exit(0)

# Reuse the exact MiCode active-window wait: the generic new helper also
# accepts the last quarter, which the tablet sequence deliberately excludes.
original = (reference / 'msm/sde/sde_encoder.c').read_text()
start = original.index('int sde_encoder_vid_wait_for_active(')
end = original.index('\nint sde_encoder_wait_for_event(', start)
wait = original[start:end].replace('int sde_encoder_vid_wait_for_active(',
                                  'static int sheng_encoder_wait_for_active(', 1)
wait = wait.replace('if (!phys || (phys->ops.is_master && !phys->ops.is_master(phys)))',
                    'if (!phys || !phys->ops.get_line_count ||\n'
                    '\t\t    (phys->ops.is_master && !phys->ops.is_master(phys)))')
before_kickoff = '''	/* MiCode N81A: change the panel rate around the video timing latch. */
	if (sde_enc->disp_info.intf_type == DRM_MODE_CONNECTOR_DSI) {
		struct drm_bridge *bridge = drm_bridge_chain_get_first_bridge(drm_enc);
		struct dsi_bridge *dsi = bridge ? container_of(bridge, struct dsi_bridge, base) : NULL;

		if (dsi && dsi->display && dsi_panel_is_sheng(dsi->display->panel) &&
		    (dsi->dsi_mode.dsi_mode_flags & DSI_MODE_FLAG_VRR)) {
			sheng_panel = dsi->display->panel;
			mutex_lock(&sheng_panel->panel_lock);
			sheng_encoder_wait_for_active(drm_enc);
			if (sheng_panel->k618_sheng_last_fps == 60 &&
			    dsi->dsi_mode.timing.refresh_rate != 120) {
				ret = dsi_panel_tx_cmd_set(sheng_panel, DSI_CMD_SET_SHENG_PEN_CLEAR, false);
				if (ret)
					SDE_ERROR("sheng pen clear failed: %d\\n", ret);
				sde_encoder_wait_for_event(drm_enc, MSM_ENC_VBLANK);
				sheng_encoder_wait_for_active(drm_enc);
			}
		}
	}

'''
after_kickoff = '''	if (sheng_panel) {
		ret = dsi_panel_tx_cmd_set(sheng_panel, DSI_CMD_SET_SHENG_TIMING_VIDEO, false);
		SDE_INFO("sheng video switch: %u -> %u rc=%d\\n",
			sheng_panel->k618_sheng_last_fps,
			sheng_panel->cur_mode->timing.refresh_rate, ret);
		mutex_unlock(&sheng_panel->panel_lock);
	}

'''
post_on = '''	if (!rc && dsi_panel_is_sheng(panel)) {
		rc = dsi_panel_tx_cmd_set(panel, DSI_CMD_SET_SHENG_TIMING_VIDEO, false);
		DSI_INFO("sheng post-on video timing: fps=%u rc=%d\\n",
			panel->cur_mode->timing.refresh_rate, rc);
	}
'''
changes = {
    'msm/dsi/dsi_defs.h': [('\tDSI_CMD_SET_MAX\n',
        '\tDSI_CMD_SET_SHENG_TIMING_VIDEO,\n\tDSI_CMD_SET_SHENG_PEN_CLEAR,\n\tDSI_CMD_SET_MAX\n')],
    'msm/dsi/dsi_panel.h': [('\tbool panel_initialized;\n',
        '\tbool panel_initialized;\n\tu32 k618_sheng_last_fps;\n'),
        ('static inline bool dsi_panel_initialized(',
         'bool dsi_panel_is_sheng(struct dsi_panel *panel);\n'
         'int dsi_panel_tx_cmd_set(struct dsi_panel *panel, enum dsi_cmd_set_type type,\n'
         '\t\tbool do_peripheral_flush);\n\nstatic inline bool dsi_panel_initialized(')],
    'msm/dsi/dsi_panel.c': [
        ('\t"mi,mdss-dsi-peak-gamma-read-pre-disable-command",\n',
         '\t"mi,mdss-dsi-peak-gamma-read-pre-disable-command",\n'
         '\t"qcom,mdss-dsi-timing-switch-video-command",\n'
         '\t"mi,mdss-dsi-dispparam-pen-clear-command",\n'),
        ('\t"mi,mdss-dsi-peak-gamma-read-pre-disable-command-state",\n',
         '\t"mi,mdss-dsi-peak-gamma-read-pre-disable-command-state",\n'
         '\t"qcom,mdss-dsi-timing-switch-video-command-state",\n'
         '\t"mi,mdss-dsi-dispparam-pen-clear-command-state",\n'),
        ('int dsi_panel_post_enable(struct dsi_panel *panel)\n',
         'bool dsi_panel_is_sheng(struct dsi_panel *panel)\n{\n\tu64 id = 0;\n\n'
         '\treturn panel && panel->panel_mode == DSI_OP_VIDEO_MODE &&\n'
         '\t\t!of_property_read_u64(panel->panel_of_node, "mi,panel-id", &id) &&\n'
         '\t\tid == 0x4e38316150360200ULL;\n}\n\n'
         'int dsi_panel_post_enable(struct dsi_panel *panel)\n'),
    ],
    'msm/dsi/dsi_display.c': [
        ('\trc = dsi_display_validate_mode_set(display, &adj_mode, flags);',
         '\tdisplay->panel->k618_sheng_last_fps = display->panel->cur_mode ?\n'
         '\t\tdisplay->panel->cur_mode->timing.refresh_rate : 0;\n\n'
         '\trc = dsi_display_validate_mode_set(display, &adj_mode, flags);')],
    'msm/sde/sde_encoder.c': [
        ('#include "dsi_display.h"\n', '#include "dsi_display.h"\n#include "dsi_drm.h"\n'),
        ('void sde_encoder_kickoff(struct drm_encoder *drm_enc, bool config_changed)\n',
         wait + '\nvoid sde_encoder_kickoff(struct drm_encoder *drm_enc, bool config_changed)\n'),
    ],
}
# Scope function-specific replacements before merging into the validated edits.
for name, function, additions in [
    ('msm/dsi/dsi_panel.c', 'int dsi_panel_post_enable(', [
        ('error:\n\tmutex_unlock(&panel->panel_lock);', post_on + 'error:\n\tmutex_unlock(&panel->panel_lock);')]),
    ('msm/sde/sde_encoder.c', 'void sde_encoder_kickoff(', [
        ('\tstruct sde_encoder_virt *sde_enc;\n', '\tstruct sde_encoder_virt *sde_enc;\n\tstruct dsi_panel *sheng_panel = NULL;\n'),
        ('\t/* All phys encs are ready to go, trigger the kickoff */', before_kickoff + '\t/* All phys encs are ready to go, trigger the kickoff */'),
        ('\tif (sde_enc->autorefresh_solver_disable &&', after_kickoff + '\tif (sde_enc->autorefresh_solver_disable &&')])]:
    body = (tree / name).read_text()
    a = body.index(function)
    b = body.index('\n}\n', a) + 3
    old = body[a:b]
    new = old
    for x, y in additions:
        assert new.count(x) == 1, (name, x)
        new = new.replace(x, y, 1)
    # The helper insertion changes the prefix but leaves this function body intact.
    changes[name].append((old, new))

hashes, prepared, diff = {}, {}, []
for name, edits in changes.items():
    before = (tree / name).read_text()
    after = before
    for old, new in edits:
        assert after.count(old) == 1, (name, old[:80])
        after = after.replace(old, new, 1)
    prepared[name] = after
    hashes[name] = dict(before=hashlib.sha256(before.encode()).hexdigest(),
                        after=hashlib.sha256(after.encode()).hexdigest())
    diff.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                 fromfile='a/'+name, tofile='b/'+name, n=3))
for name, text in prepared.items():
    (tree / name).write_text(text)
patch.write_text(''.join(diff))
receipt.write_text(json.dumps(dict(
    reference_repository='https://github.com/MiCode/vendor_opensource_display-drivers',
    reference_revision='6461221b68908b990e1fa2b60feaa812cb944ef5',
    upstream_revision='c3956156ce7c4193c451dfda531fad72d35bfebb',
    scope='N81A post-on and VRR kickoff timing commands, active-window wait, 60Hz pen-clear sequence',
    hardware_values='all command payloads remain parsed from original sheng DT; no new register values',
    panel_id='0x4e38316150360200', files=hashes,
    hardware_result='pending', initial_splash_corruption_fixed_claimed=False,
    screen_corruption_fixed_claimed=False), indent=2)+'\n')
print('N81A video timing sequence applied', flush=True)
