#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Opt-in bootloader intent for normal/emergency restart and pre-stop panic capture."""
import difflib
import hashlib
import json
from build_sheng618_upstream import ACK, PROJECT

changes = {
    'kernel/reboot.c': [
        ('#include <linux/reboot.h>\n', '#include <linux/reboot.h>\n#include <linux/sheng_bootlog.h>\n'),
        ('\tmachine_emergency_restart();',
         '\tif (sheng_bootlog_test_mode())\n\t\tmachine_restart("bootloader");\n'
         '\telse\n\t\tmachine_emergency_restart();'),
        ('void kernel_restart(char *cmd)\n{\n',
         'void kernel_restart(char *cmd)\n{\n\tif (sheng_bootlog_test_mode())\n'
         '\t\tcmd = "bootloader";\n'),
    ],
    'kernel/panic.c': [
        ('#include <linux/reboot.h>\n', '#include <linux/reboot.h>\n#include <linux/sheng_bootlog.h>\n'),
        ('\tkgdb_panic(buf);', '\tsheng_bootlog_panic_pause();\n\tkgdb_panic(buf);'),
    ],
}
receipt = PROJECT / 'reports/kernel618-test-reboot-source.json'
previous = json.loads(receipt.read_text()) if receipt.exists() else None
patch, hashes = [], {}
for relative, replacements in changes.items():
    path = ACK / relative
    before = path.read_text()
    if previous and hashlib.sha256(before.encode()).hexdigest() == previous['files'][relative]['after']:
        for old, new in reversed(replacements):
            assert before.count(new) == 1
            before = before.replace(new, old, 1)
    after = before
    for old, new in replacements:
        assert after.count(old) == 1, (relative, old)
        after = after.replace(old, new, 1)
    path.write_text(after)
    hashes[relative] = dict(before=hashlib.sha256(before.encode()).hexdigest(),
                            after=hashlib.sha256(after.encode()).hexdigest())
    patch.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                 fromfile='a/' + relative, tofile='b/' + relative, n=0))
(PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/test-reboot.patch').write_text(''.join(patch))
receipt.write_text(json.dumps(dict(files=hashes,
    enabled_only_by='sheng_bootlog.test_timeout=180 (valid range 10..600 for QEMU)',
    reference='ACK ff4a6c3bb0f471a9dd186293a47b62c83829b97d normal/emergency restart and panic before other CPUs stop; selected qcom-reboot-reason DT cell writes 0x02',
    default_enabled=False, preserves_exported_function_signatures=True,
    limits='Requires scheduled CPU, restart provider and PMIC reason support; hardware reset before provider probe is not guaranteed'), indent=2) + '\n')
