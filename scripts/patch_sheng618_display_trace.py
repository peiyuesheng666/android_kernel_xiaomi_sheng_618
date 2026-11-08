#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Add sleepable probe checkpoints so the existing disk logger can persist them."""
import difflib
import hashlib
import json

from build_sheng618_upstream import K618, PROJECT

tree = K618 / 'vendor/qcom/opensource/display-drivers'
folder = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18'
receipt = PROJECT / 'reports/kernel618-display-probe-trace-source.json'
header = '''/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SHENG_BOOT_TRACE_H
#define SHENG_BOOT_TRACE_H
#include <linux/delay.h>
#include <linux/printk.h>

/* Diagnostic image only. Call only from sleepable display probe context.
 * Give the 250 ms rawdump worker time to persist the last completed stage.
 */
static inline void sheng_probe_checkpoint(const char *stage)
{
\tpr_notice("sheng_display_probe: %s\\n", stage);
\tmsleep(350);
}
#endif
'''

def cp(stage):
    return '\tsheng_probe_checkpoint("' + stage + '");\n'

changes = {
    'msm/msm_drv.c': [
        ('#include "hfi_msm_drv.h"\n', '#include "hfi_msm_drv.h"\n#include "sheng_boot_trace.h"\n'),
        ('\tret = (kms)->funcs->hw_init(kms);', cp('hw_init begin') + '\tret = (kms)->funcs->hw_init(kms);\n' + cp('hw_init returned')),
        ('\tmsm_drm_notify_components(ddev, MSM_COMP_OBJECT_CREATED);', cp('components initialized') + '\tmsm_drm_notify_components(ddev, MSM_COMP_OBJECT_CREATED);'),
        ('\t\tret = msm_irq_install(ddev, platform_get_irq(pdev, 0));', cp('IRQ install begin') + '\t\tret = msm_irq_install(ddev, platform_get_irq(pdev, 0));\n' + cp('IRQ install returned')),
        ('\tdrm_mode_config_reset(ddev);', cp('mode_config_reset begin') + '\tdrm_mode_config_reset(ddev);\n' + cp('mode_config_reset returned')),
        ('\t\tret = kms->funcs->cont_splash_config(kms, NULL);', cp('cont_splash_config begin') + '\t\tret = kms->funcs->cont_splash_config(kms, NULL);\n' + cp('cont_splash_config returned')),
        ('\tret = drm_dev_register(ddev, 0);', cp('drm_dev_register begin') + '\tret = drm_dev_register(ddev, 0);\n' + cp('drm_dev_register returned')),
        ('\t\tret = kms->funcs->postinit(kms);', cp('postinit begin') + '\t\tret = kms->funcs->postinit(kms);\n' + cp('postinit returned')),
    ],
    'msm/sde/sde_kms.c': [
        ('#include "hfi_kms.h"\n', '#include "hfi_kms.h"\n#include "../sheng_boot_trace.h"\n'),
        ('\t/* Create the planes */', cp('display connectors setup returned') + '\t/* Create the planes */'),
        ('\t\tcrtc = sde_crtc_init(dev, primary_planes[i]);',
         '\t\tpr_notice("sheng_display_probe: CRTC %d/%d begin\\n", i, max_crtc_count);\n\t\tmsleep(350);\n'
         '\t\tcrtc = sde_crtc_init(dev, primary_planes[i]);\n'
         '\t\tpr_notice("sheng_display_probe: CRTC %d/%d returned, error=%ld\\n",\n'
         '\t\t\ti, max_crtc_count, IS_ERR(crtc) ? PTR_ERR(crtc) : 0L);\n\t\tmsleep(350);'),
        ('\trc = _sde_kms_drm_obj_init(sde_kms);', cp('DRM objects begin') + '\trc = _sde_kms_drm_obj_init(sde_kms);\n' + cp('DRM objects returned')),
        ('\trc = _sde_kms_hw_init_blocks(sde_kms, dev, priv);', cp('hardware blocks begin') + '\trc = _sde_kms_hw_init_blocks(sde_kms, dev, priv);\n' + cp('hardware blocks returned')),
        ('\tif (sde_in_trusted_vm(sde_kms)) {\n\t\trc = sde_vm_trusted_init', cp('VM init begin') + '\tif (sde_in_trusted_vm(sde_kms)) {\n\t\trc = sde_vm_trusted_init'),
        ('\tif (test_bit(SDE_FEATURE_DISP_OP, sde_kms->catalog->features))\n\t\tsde_kms->hfi_session_start', cp('VM init returned') + '\tif (test_bit(SDE_FEATURE_DISP_OP, sde_kms->catalog->features))\n\t\tsde_kms->hfi_session_start'),
        ('\tsde_kms_handle_power_event(SDE_POWER_EVENT_POST_ENABLE, sde_kms);', cp('postinit power event begin') + '\tsde_kms_handle_power_event(SDE_POWER_EVENT_POST_ENABLE, sde_kms);\n' + cp('postinit power event returned')),
    ],
}

previous = json.loads(receipt.read_text()) if receipt.is_file() else None
files, patch = {}, []
prepared = {}
for name, replacements in changes.items():
    before = (tree / name).read_text()
    if previous and hashlib.sha256(before.encode()).hexdigest() == previous['files'][name]['after']:
        for old, new in reversed(replacements):
            assert before.count(new) == 1, (name, new)
            before = before.replace(new, old, 1)
    after = before
    for old, new in replacements:
        assert after.count(old) == 1, (name, old, after.count(old))
        after = after.replace(old, new, 1)
    prepared[name] = after
    files[name] = {'before': hashlib.sha256(before.encode()).hexdigest(),
                   'after': hashlib.sha256(after.encode()).hexdigest()}
    patch.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                    fromfile='a/' + name, tofile='b/' + name, n=0))
for name, data in prepared.items():
    (tree / name).write_text(data)
(tree / 'msm/sheng_boot_trace.h').write_text(header)
(folder / 'sheng_boot_trace.h').write_text(header)
(folder / 'display-probe-trace.patch').write_text(''.join(patch))
report = dict(files=files, header_sha256=hashlib.sha256(header.encode()).hexdigest(),
              patch_context_lines=0,
              checkpoint_delay_ms=350, logger_interval_ms=250,
              scope='sleepable display probe diagnostics only; no DP/HFI feature changes',
              basis='r7 rawdump ends at 12.516 s without final Oops; compare selected nuwa base, LOS 92a9fde479d3262da080cfd28bab0775b0da500a, MiCode 6461221b68908b990e1fa2b60feaa812cb944ef5',
              source_tree=str(tree))
receipt.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
