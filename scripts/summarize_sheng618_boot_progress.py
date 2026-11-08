#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarize measured boot module durations and actual dual-backlight registers."""
import argparse
import hashlib
import json
import re
from test_sheng618_hardware import ROOT

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', required=True)
options = parser.parse_args()
assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}', options.revision)
receipt = json.loads((ROOT/'reports'/('kernel618-'+options.revision+'-automation.json')).read_text())
assert receipt['log_readback_succeeded']
path = (ROOT/receipt['latest_log']).resolve()
assert path.is_relative_to((ROOT/'reports/device'/('kernel618-'+options.revision)).resolve())
text = path.read_text(errors='replace')
lines = list(dict.fromkeys(text.splitlines()))
modules, batch, dark, bright = [], {}, [], []
for line in lines:
    stamp = re.search(r'\[\s*(\d+\.\d+)\]', line)
    if not stamp:
        continue
    uptime = float(stamp[1])
    module = re.search(r'k618_load: (\d+)/(\d+) (\S+): loaded \((\d+) ms\)', line)
    if module:
        modules.append(dict(index=int(module[1]), name=module[3], duration_ms=int(module[4]), uptime=uptime))
    if re.search(r'k618_load: \d+ modules from', line):
        batch['start_seconds'] = uptime
    if 'k618_load: done:' in line:
        batch['finish_seconds'] = uptime
        batch['summary'] = line.split('k618_load: done:', 1)[1].strip()
    chip = re.search(r'ktz8866 (\d+-0011):', line)
    readback = re.search(r'boot_dark actual=(\d+) enable=0x([0-9a-f]+) previous_enable=0x([0-9a-f]+)', line)
    if chip and readback:
        dark.append(dict(chip=chip[1], uptime=uptime, actual=int(readback[1]), enable=int(readback[2],16), previous_enable=int(readback[3],16)))
    readback = re.search(r'sheng_backlight requested=(\d+).*actual=(\d+) enable=0x([0-9a-f]+) write_rc=(-?\d+)', line)
    if chip and readback and int(readback[1]) > 0:
        bright.append(dict(chip=chip[1], uptime=uptime, requested=int(readback[1]), actual=int(readback[2]), enable=int(readback[3],16), write_rc=int(readback[4])))
if 'start_seconds' in batch and 'finish_seconds' in batch:
    batch['elapsed_seconds'] = round(batch['finish_seconds']-batch['start_seconds'],6)
report = dict(revision=options.revision, run=receipt['run'], evidence=str(path.relative_to(ROOT)),
    sha256=hashlib.sha256(path.read_bytes()).hexdigest(), batch=batch,
    measured_module_count=len(modules), measured_module_duration_ms=sum(m['duration_ms'] for m in modules),
    slowest_modules=sorted(modules,key=lambda m:m['duration_ms'],reverse=True)[:12],
    boot_dark_readbacks=dark, first_nonzero_backlights=bright[:2],
    limitation='Kernel uptime only; module init timing does not include all asynchronous probe work. Visual white flash and perceived boot time require physical acceptance.')
(ROOT/'reports'/('kernel618-'+options.revision+'-progress.json')).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
