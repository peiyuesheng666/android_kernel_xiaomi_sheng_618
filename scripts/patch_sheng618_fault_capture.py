#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Keep arm64 exception diagnostics alive briefly for the existing disk writer."""
import difflib
import hashlib
import json
import shutil

from build_sheng618_upstream import ACK, PROJECT

source = ACK / 'arch/arm64/kernel/traps.c'
receipt = PROJECT / 'reports/kernel618-fault-capture-source.json'
folder = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18'
replacements = [
    ('#include <linux/kdebug.h>\n', '#include <linux/kdebug.h>\n#include <linux/sheng_bootlog.h>\n'),
    ('\tdump_kernel_instr(addr);\n', '\tdump_kernel_instr(addr);\n\tsheng_bootlog_fault_pause();\n'),
]
before = source.read_text()
if receipt.is_file():
    previous = json.loads(receipt.read_text())
    if hashlib.sha256(before.encode()).hexdigest() == previous['after']:
        for old, new in reversed(replacements):
            assert before.count(new) == 1
            before = before.replace(new, old, 1)
after = before
for old, new in replacements:
    assert after.count(old) == 1, (old, after.count(old))
    after = after.replace(old, new, 1)
source.write_text(after)
shutil.copyfile(folder / 'sheng_bootlog.h', ACK / 'include/linux/sheng_bootlog.h')
(folder / 'arm64-fault-capture.patch').write_text(''.join(difflib.unified_diff(
    before.splitlines(True), after.splitlines(True), fromfile='a/arch/arm64/kernel/traps.c',
    tofile='b/arch/arm64/kernel/traps.c', n=0)))
report = dict(source=str(source), before=hashlib.sha256(before.encode()).hexdigest(),
              after=hashlib.sha256(after.encode()).hexdigest(),
              header_sha256=hashlib.sha256((folder / 'sheng_bootlog.h').read_bytes()).hexdigest(),
              call_site='arm64 __die, after show_regs and dump_kernel_instr, before panic',
              pause_ms=1500, maximum_pause_count=1,
              writer_explicitly_queued_on_other_online_cpu=True,
              block_io_in_exception_context=False, requires_other_cpu_and_working_storage_irq=True,
              reference='selected ACK ff4a6c3bb0f471a9dd186293a47b62c83829b97d arch/arm64/kernel/traps.c',
              limitation='Cannot capture a hard hang that does not enter __die; no safe panic-context block writer')
receipt.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
