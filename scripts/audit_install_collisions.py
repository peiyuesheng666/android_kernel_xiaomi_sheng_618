#!/usr/bin/env python3
"""Compare resolved product file copies against existing Soong install rules."""
import json
import argparse
from pathlib import Path
import re

WORK = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--require-clean', action='store_true')
args = parser.parse_args()
ROM = Path('/root/sheng-lineage/lineage-24.0')
LOGS = ROM.parent / 'logs'
makefile = ROM / 'out/soong/installs-lineage_sheng.mk'
prefix = 'out/target/product/sheng/'
targets = set()
with makefile.open() as stream:
    for line in stream:
        if line.startswith(prefix) and ':' in line:
            targets.add(line.split(':', 1)[0])
collisions = []
copies = []
for pair in (LOGS / 'product-copy-files.txt').read_text().split():
    fields = pair.split(':')
    if len(fields) < 2 or not re.match(r'^(?:system|system_ext|product|vendor|odm|root|recovery)/', fields[1]):
        continue
    copies.append(pair)
    if prefix + fields[1] in targets:
        collisions.append({'source': fields[0], 'destination': fields[1]})
report = {'copy_pairs_checked': len(copies), 'soong_install_targets': len(targets),
          'collisions': collisions, 'uses_previous_soong_snapshot': True}
(WORK / 'reports/install-collisions.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
if args.require_clean and collisions:
    raise SystemExit(1)
