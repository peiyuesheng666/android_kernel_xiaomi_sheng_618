#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record official tag description and local controller/interface evidence."""
import hashlib
import json
import urllib.request
from build_sheng618_upstream import ROOT, PROJECT

references = []
for name, url in [
    ('nfc-spec.html', 'https://www.mi.com/global/product/xiaomi-pad-6s-pro-124/specs/'),
    ('nfc-overview.html', 'https://www.mi.com/global/product/xiaomi-pad-6s-pro-124/'),
]:
    path = ROOT/'diagnostic'/name
    if not path.exists():
        path.write_bytes(urllib.request.urlopen(url, timeout=25).read())
    assert 'Supports NFC tag' in path.read_text()
    references.append(dict(url=url, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
dt = ROOT/'diagnostic/disklog-r5/live.dts'
matches = [line.strip() for line in dt.read_text().splitlines()
           if any(term in line.lower() for term in ['nfc', 'pn544', 'pn547', 'pn553', 'nq-nci', 'st21nfc'])]
report = dict(references=references, official_wording='Supports NFC tag',
    official_behavior='Phone touches tablet NFC area to initiate Xiaomi Share photos/files transfer',
    live_dt_sha256=hashlib.sha256(dt.read_bytes()).hexdigest(), live_dt_matches=matches,
    device_evidence='reports/kernel618-hardware-r26-switches.json',
    result='No active NFC controller/service found; official feature is NFC-tag initiated sharing. No fabricated controller or service added.',
    limitation='Physical tag interaction and actual Xiaomi Share transfer require another compatible device')
(PROJECT/'reports/kernel618-nfc-audit.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
