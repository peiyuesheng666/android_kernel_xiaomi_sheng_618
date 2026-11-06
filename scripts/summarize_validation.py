#!/usr/bin/env python3
"""Record every failed validation target, without treating validation as a ROM."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from validation_inputs import fingerprint

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--returncode', type=int, required=True)
args = parser.parse_args()
work = Path(__file__).resolve().parents[1]
logs = Path('/root/sheng-lineage/logs')
text = (logs / 'build-lineage.log').read_text(errors='replace')
text = re.sub(r'\x1b\[[0-9;]*m', '', text)
failed = []
for match in re.finditer(r'^FAILED: (.+)$', text, re.M):
    target = match.group(1)
    if target != 'ninja: ' and target.strip() != 'ninja:':
        failed.append(target)
diagnostics = [line for line in text.splitlines() if re.search(
    r"(^[A-Za-z0-9_./@+-]+: error:|:ERROR |:\d+(?::\d+)?: (?:fatal )?error:|^fatal error:|^error:|neverallow.*failed|ABI check failed|CRC mismatch|unresolved symbol)", line)]
report = {
    'recorded_at': datetime.now(timezone.utc).isoformat(),
    'targets': (logs / 'validation-targets.txt').read_text().splitlines(),
    'returncode': args.returncode,
    'validation_passed': args.returncode == 0,
    'failed_targets': list(dict.fromkeys(failed)),
    'diagnostics': list(dict.fromkeys(diagnostics)),
    'log': str(logs / 'build-lineage.log'),
    'rom_compiled': False,
    'hardware_boot_tested': False,
}
if args.returncode == 0:
    report['validated_inputs'] = fingerprint()
(work / 'reports/lineage-validation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
