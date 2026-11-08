#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restore the required eUSB2 source-clock acquisition in the selected integration."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

from build_sheng618_upstream import K618, PROJECT, ROOT

relative = 'drivers/usb/phy/phy-msm-snps-eusb2.c'
path = K618 / 'soc' / relative
before = subprocess.check_output(['git', '-C', K618 / 'soc', 'show', 'HEAD:' + relative], text=True)
old = '''		phy->ref_clk = devm_clk_get(dev, "ref_clk");
		if (IS_ERR(phy->ref_clk)) {
			dev_err(dev, "clk get failed for ref_clk\\n");
			ret = PTR_ERR(phy->ref_clk);
			goto err_ret;
		}
'''
new = old.replace('ref_clk', 'ref_clk_src')
assert before.count(old) == 1
after = before.replace(old, new, 1)
assert path.read_text() in (before, after), 'Unexpected local USB PHY edits'
references = []
for name in ('lineage-kernel', 'micode-kernel'):
    root = ROOT / 'src' / name
    source = root / relative
    text = source.read_text()
    assert 'phy->ref_clk_src = devm_clk_get(dev, "ref_clk_src");' in text
    references.append(dict(repository=name,
        commit=subprocess.check_output(['git', '-C', root, 'rev-parse', 'HEAD'], text=True).strip(),
        file=relative, sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
path.write_text(after)
folder = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18'
(folder / 'sheng-usb-refclock.patch').write_text(''.join(difflib.unified_diff(
    before.splitlines(True), after.splitlines(True), fromfile='a/' + relative, tofile='b/' + relative)))
report = dict(
    files={'soc/' + relative: dict(before=hashlib.sha256(before.encode()).hexdigest(),
                                  after=hashlib.sha256(after.encode()).hexdigest())},
    references=references,
    cause='ref_clk was acquired twice; ref_clk_src remained NULL, making clk_get_rate return 0',
    change='Acquire the required ref_clk_src and propagate its errors, including EPROBE_DEFER',
    dt_binding='sheng hsphy@88e3000: ref_clk_src = RPMH_CXO_PAD_CLK; ref_clk remains separate',
    guessed_clock_rate=False, shared_clock_tree_changed=False,
    hardware_result='pending')
(PROJECT / 'reports/kernel618-usb-refclock-source.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
