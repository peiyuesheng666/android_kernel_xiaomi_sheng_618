#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Balance successful DP AUX registration before releasing its backing object."""
import difflib
import hashlib
import json

from build_sheng618_upstream import K618, PROJECT

tree = K618 / 'vendor/qcom/opensource/display-drivers'
folder = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18'
receipt = PROJECT / 'reports/kernel618-dp-aux-lifetime-source.json'
changes = {
    'msm/dp/dp_aux.c': [
        ('\taux = container_of(dp_aux, struct dp_aux_private, dp_aux);\n\tdrm_dp_aux_unregister(&aux->drm_aux);',
         '\t/* drm_aux is published only after successful registration. */\n'
         '\tif (!dp_aux->drm_aux)\n\t\treturn;\n\n'
         '\taux = container_of(dp_aux, struct dp_aux_private, dp_aux);\n'
         '\tdrm_dp_aux_unregister(&aux->drm_aux);\n\tdp_aux->drm_aux = NULL;'),
        ('\tmutex_destroy(&aux->mutex);\n\n\tdevm_kfree(aux->dev, aux);',
         '\t/* Includes post-init failures after AUX registration (e.g. PLL). */\n'
         '\tdp_aux_deregister(dp_aux);\n\tmutex_destroy(&aux->mutex);\n\n'
         '\tdevm_kfree(aux->dev, aux);'),
    ],
    'msm/dp/dp_display.c': [
        ('error_pll:\n\tdp_aux_put(dp->aux);\nerror_aux:',
         'error_pll:\n\tdp_aux_put(dp->aux);\n\tdp->aux = NULL;\nerror_aux:'),
    ],
}
previous = json.loads(receipt.read_text()) if receipt.is_file() else None
files, patch, prepared = {}, [], {}
for name, replacements in changes.items():
    before = (tree / name).read_text()
    if previous and hashlib.sha256(before.encode()).hexdigest() == previous['files'][name]['after']:
        for old, new in reversed(replacements):
            assert before.count(new) == 1, (name, new)
            before = before.replace(new, old, 1)
    after = before
    for old, new in replacements:
        assert after.count(old) == 1, (name, old)
        after = after.replace(old, new, 1)
    prepared[name] = after
    files[name] = {'before': hashlib.sha256(before.encode()).hexdigest(),
                   'after': hashlib.sha256(after.encode()).hexdigest()}
    patch.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                    fromfile='a/' + name, tofile='b/' + name, n=0))
for name, data in prepared.items():
    (tree / name).write_text(data)
(folder / 'dp-aux-lifetime.patch').write_text(''.join(patch))
report = dict(files=files,
    evidence='r11 run 6080c2fc01074de6: stale kset entry at offset 480; dp_aux_put free stack, sde_hw_sspp_init reuse allocation stack',
    trigger='Stock sheng lacks the newer separate qcom,dp-pll phandle: error unwind frees a registered AUX I2C adapter',
    fix='The AUX owner unregisters before free; successful-registration pointer guards repeated/failed unregister; error unwind clears dp->aux',
    references=[
        dict(tree='/root/sheng-618/upstream-project', commit='c3956156ce7c4193c451dfda531fad72d35bfebb',
             result='Selected nuwa/HyperOS integration retains upstream DP registration-before-PLL failure path'),
        dict(tree='/root/sheng-618/src/lineage-modules', commit='92a9fde479d3262da080cfd28bab0775b0da500a',
             result='Same dp_aux_put omission; not a ready-made fix for failed initialization'),
        dict(tree='/root/sheng-618/src/micode-display', commit='6461221b68908b990e1fa2b60feaa812cb944ef5',
             result='Same cleanup omission; old in-node PLL binding avoids this particular trigger on sheng'),
        dict(tree='ACK', commit='ff4a6c3bb0f471a9dd186293a47b62c83829b97d',
             result='drm_dp_aux_register adds embedded I2C device; drm_dp_aux_unregister removes it before owner memory may be freed')],
    scope='DP AUX lifetime fix; legacy PLL binding and external-display functionality remain unfinished',
    source_tree=str(tree))
receipt.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
