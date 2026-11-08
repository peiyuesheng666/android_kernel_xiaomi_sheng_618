#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restore N81A stock initial brightness and preserve bootloader scanout at probe."""
import difflib
import hashlib
import json
from build_sheng618_upstream import ROOT, PROJECT, K618

prefix = 'vendor/qcom/opensource/display-drivers/'
backup = ROOT/'diagnostic/hardware-r34/boot-handoff-before'
receipt_path = PROJECT/'reports/kernel618-boot-handoff-source.json'
prior = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
files, payloads, patch = {}, {}, []
for relative in ['msm/sde/sde_connector.c', 'msm/sheng_ktz8866.c']:
    name = prefix+relative
    path = K618/name
    saved = backup/name
    current = path.read_bytes()
    if not saved.exists():
        assert prior is None, 'Missing immutable baseline'
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(current)
    before = saved.read_bytes()
    digest = lambda data: hashlib.sha256(data).hexdigest()
    assert current == before or (prior and digest(current) == prior['files'][name]['after'])
    if prior:
        assert digest(before) == prior['files'][name]['before']
    text = before.decode()
    if relative.endswith('sde_connector.c'):
        old = '\tprops.brightness = bl_config->brightness_max_level;\n'
        assert text.count(old) == 1
        text = text.replace(old, old+'''\t/* MiCode sheng and LOS use the DT initial level, not maximum brightness.
\t * Keep this tablet adaptation local to the N81A external-backlight panel. */
\t{
\t\tu64 panel_id;
\t\tu32 initial;

\t\tif (display->panel->bl_config.type == DSI_BACKLIGHT_EXTERNAL &&
\t\t    !of_property_read_u64(display->panel->panel_of_node,
\t\t\t"mi,panel-id", &panel_id) && panel_id == 0x4e38316150360200ULL &&
\t\t    !of_property_read_u32(display->panel->panel_of_node,
\t\t\t"qcom,mdss-brightness-init-level", &initial)) {
\t\t\tprops.brightness = min_t(u32, initial, props.max_brightness);
\t\t\tSDE_INFO("sheng initial backlight=%u max=%u\\n",
\t\t\t\tprops.brightness, props.max_brightness);
\t\t}
\t}
''', 1)
    else:
        a = text.index('\t/* Continuous splash may skip dsi_panel_reset entirely.')
        b = text.index('\n\tmutex_lock(&ktz8866_dev_list_mutex)', a)
        assert text[a:b].count('ktz_update_status(pdata, 0)') == 1
        text = text[:a]+'''\t/* Probe must preserve the bootloader image. The actual panel reset
\t * path darkens these LEDs before invalidating scanout. */
'''+text[b:]
    after = text.encode()
    payloads[name] = after
    files[name] = dict(before=digest(before), after=digest(after))
    patch.extend(difflib.unified_diff(before.decode().splitlines(True), text.splitlines(True),
                                    fromfile='a/'+name, tofile='b/'+name))
for name, data in payloads.items():
    (K618/name).write_bytes(data)
(PROJECT/'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-boot-handoff.patch').write_text(''.join(patch))
report = dict(files=files, backup=str(backup),
    references=dict(micode_display='6461221b68908b990e1fa2b60feaa812cb944ef5',
                    los_nuwa_display='92a9fde479d3262da080cfd28bab0775b0da500a'),
    reference_behavior='Both fixed reference connector implementations initialize props.brightness from brightness_init_level; MiCode KTZ probe does not darken the bootloader image',
    stock_dt_panel_id='0x4e38316150360200',stock_initial_brightness=307,stock_max_brightness=4095,
    evidence='r33 initial requested4095; probe LEDs0 at13.323/13.338s; first nonzero40.943s; user reports white flash and black interval',
    adaptation='Read existing DT initial brightness only for N81A; remove our probe-only LED blackout; retain pre-reset LED off, bias and normal brightness routing',
    hardware_result='pending')
receipt_path.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
