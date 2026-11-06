#!/usr/bin/env python3
"""Find unresolved type/attribute references in common expanded policy rules.

This supplements checkpolicy; it is not a complete SELinux grammar validator.
"""
import json
from pathlib import Path
import re

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
conf = rom / 'out/soong/.intermediates/system/sepolicy/vendor_sepolicy.conf/android_common/sheng/vendor_sepolicy.conf'
source = conf.read_text()
# Strip comments without changing character offsets, for useful line references.
text = re.sub(r'#[^\n]*', lambda m: ' ' * len(m[0]), source)
identifier = r'[A-Za-z_][A-Za-z0-9_-]*'
known = set(re.findall(r'(?m)^\s*(?:type|attribute|attribute_role)\s+(' + identifier + ')', text))
for aliases in re.findall(r'\btypealias\s+' + identifier + r'\s+alias\s+([^;]+);', text):
    known.update(re.findall(identifier, aliases))
known.update(('self', 'notself'))
type_set = rf'(?:~?\s*\{{[^}}]*\}}|~?\s*{identifier})'
patterns = [
    rf'(?m)^\s*(?:allow|neverallow|auditallow|dontaudit)\s+({type_set})\s+({type_set})\s*:',
    rf'(?m)^\s*typeattribute\s+({identifier})\s+({identifier})\s*;',
    rf'(?m)^\s*(?:type_transition|type_change|type_member)\s+({type_set})\s+({type_set})\s*:\s*{identifier}\s+({identifier})',
]
unknown = {}
for pattern in patterns:
    for match in re.finditer(pattern, text):
        for group in match.groups():
            for name in re.findall(identifier, group):
                if name not in known:
                    unknown.setdefault(name, set()).add(source.count('\n', 0, match.start()) + 1)
findings = []
for name, lines in sorted(unknown.items()):
    references = []
    for file in (work / 'device/xiaomi/sheng/sepolicy').rglob('*'):
        if file.is_file():
            for number, line in enumerate(file.read_text().splitlines(), 1):
                if re.search(r'\b' + re.escape(name) + r'\b', line):
                    references.append({'file': str(file.relative_to(work)), 'line': number, 'text': line})
    findings.append({'name': name, 'expanded_conf_lines': sorted(lines), 'device_references': references})
report = {'conf': str(conf), 'declared_types_and_attributes': len(known),
          'unknown_references': findings,
          'scope': 'AV rules, typeattribute and type transition rules; checkpolicy remains authoritative',
          'automatic_changes': False}
(work / 'reports/policy-type-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
