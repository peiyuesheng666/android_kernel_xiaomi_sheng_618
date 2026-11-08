#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Remove only the r8 diagnostic display sleeps, preserving hardware timing."""
import difflib
import hashlib
import json
from build_sheng618_upstream import K618, PROJECT, ROOT

prefix = 'vendor/qcom/opensource/display-drivers/'
backup = ROOT/'diagnostic/hardware-r32/display-latency-before'
receipt_path = PROJECT/'reports/kernel618-display-latency-source.json'
prior = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
names = [prefix+'msm/sheng_boot_trace.h', prefix+'msm/sde/sde_kms.c']
prepared, files, patch = {}, {}, []


def sha(data):
    return hashlib.sha256(data).hexdigest()


for name in names:
    path = K618/name
    current = path.read_bytes()
    saved = backup/name
    if not saved.exists():
        assert prior is None, 'Missing immutable source snapshot'
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(current)
    before = saved.read_bytes()
    if prior:
        assert sha(before) == prior['files'][name]['before']
        assert sha(current) in (sha(before), prior['files'][name]['after']), name
    else:
        assert current == before, name
    text = before.decode()
    if name.endswith('sheng_boot_trace.h'):
        assert text.count('\tmsleep(350);\n') == 1
        text = text.replace('#include <linux/delay.h>\n', '')
        text = text.replace('/* Diagnostic image only. Call only from sleepable display probe context.\n'
                            ' * Give the 250 ms rawdump worker time to persist the last completed stage.\n'
                            ' */',
                            '/* Keep diagnostic stage markers without delaying normal boot. */')
        text = text.replace('\tmsleep(350);\n', '')
    else:
        old = ('\t\tpr_notice("sheng_display_probe: CRTC %d/%d begin\\n", i, max_crtc_count);\n'
               '\t\tmsleep(350);\n'
               '\t\tcrtc = sde_crtc_init(dev, primary_planes[i]);\n'
               '\t\tpr_notice("sheng_display_probe: CRTC %d/%d returned, error=%ld\\n",\n'
               '\t\t\ti, max_crtc_count, IS_ERR(crtc) ? PTR_ERR(crtc) : 0L);\n'
               '\t\tmsleep(350);')
        assert text.count(old) == 1, 'CRTC diagnostic context changed'
        text = text.replace(old, old.replace('\n\t\tmsleep(350);', ''), 1)
    after = text.encode()
    prepared[name] = after
    files[name] = dict(before=sha(before), after=sha(after))
    patch.extend(difflib.unified_diff(before.decode().splitlines(True), text.splitlines(True),
                                    fromfile='a/'+name, tofile='b/'+name, n=3))

for name, data in prepared.items():
    (K618/name).write_bytes(data)
folder = PROJECT/'device/xiaomi/sheng/interfaces/kernel/6.18'
(folder/'sheng_boot_trace.h').write_bytes(prepared[names[0]])
(folder/'sheng-display-latency.patch').write_text(''.join(patch))
report = dict(files=files, source_tree=str(K618), backup=str(backup),
    basis='Remove waits introduced by scripts/patch_sheng618_display_trace.py in r8; selected upstream and LOS references in kernel618-display-probe-trace-source.json do not require them.',
    diagnostic_delay_ms=0, removed_sleep_sites=3,
    scope='Diagnostic checkpoint header and two CRTC-loop waits only; retain all logs, panel reset, power and hardware timing.',
    hardware_result='pending')
receipt_path.write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
