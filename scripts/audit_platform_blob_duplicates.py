#!/usr/bin/env python3
"""Audit direct vendor-available platform source libraries duplicated as stock blobs."""
import json
from pathlib import Path
import re

WORK = Path(__file__).resolve().parents[1]
ROM = Path('/root/sheng-lineage/lineage-24.0')
inventory = WORK / 'device/xiaomi/sheng/proprietary-files.txt'
entries = {}
for line in inventory.read_text().splitlines():
    if not line or line.startswith('#'):
        continue
    destination = line.lstrip('-').split(';')[0].split('|')[0].split(':')[-1]
    path = Path(destination)
    if destination.startswith(('vendor/lib/', 'vendor/lib64/')) and path.parent.name in ('lib', 'lib64') and path.suffix == '.so':
        entries.setdefault(path.stem, []).append(line)

comments = re.compile(r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*.*?\*/', re.S)
strings = re.compile(r'"(?:\\.|[^"\\])*"')
findings = []
for relative in (ROM / 'out/.module_paths/Android.bp.list').read_text().splitlines():
    # Limit automatic candidates to platform source domains. QTI device-specific
    # namespaces and vendor implementations must be reviewed separately.
    if not relative.startswith(('system/', 'frameworks/', 'hardware/interfaces/', 'bionic/', 'external/', 'art/', 'libcore/')):
        continue
    file = ROM / relative
    if not file.is_file():
        continue
    clean = comments.sub(lambda match: match[1] or ' ', file.read_text())
    masked = strings.sub(lambda match: ' ' * len(match[0]), clean)
    for match in re.finditer(r'(?m)^\s*cc_library(?:_shared)?\s*\{', masked):
        depth, end = 1, match.end()
        while depth and end < len(masked):
            depth += (masked[end] == '{') - (masked[end] == '}')
            end += 1
        body = clean[match.end():end - 1]
        name = re.search(r'\bname\s*:\s*"([^"]+)"', body)
        if not name or name[1] not in entries:
            continue
        if re.search(r'\bvendor_available\s*:\s*true', body) and not re.search(r'\b(?:vendor|proprietary|soc_specific)\s*:\s*true', body):
            findings.append({'module': name[1], 'source': relative, 'entries': entries[name[1]]})
report = {'candidates': findings, 'automatic_changes': False}
(WORK / 'reports/platform-blob-duplicates.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
