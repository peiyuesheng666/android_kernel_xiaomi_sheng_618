#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restore the stock sheng read-only USB HAL capability and DT host override alias."""
import difflib
import hashlib
import json
import subprocess
from build_sheng618_upstream import ROOT, K618, PROJECT

relative = 'drivers/usb/repeater/repeater-qti-pmic-eusb2.c'
path = K618/'soc'/relative
before = subprocess.check_output(['git', '-C', K618/'soc', 'show', 'HEAD:'+relative], text=True)
after = before.replace('#ifdef OPLUS_FEATURE_CHG_BASIC\n#include <linux/proc_fs.h>\n#endif',
                       '#include <linux/proc_fs.h>\n#include <linux/seq_file.h>', 1)
assert after != before
after = after.replace('\tstruct dentry\t\t*root;\n',
                      '\tstruct dentry\t\t*root;\n\tstruct proc_dir_entry\t*sheng_ms_enable;\n', 1)
marker = 'static int eusb2_repeater_probe(struct platform_device *pdev)\n'
assert after.count(marker) == 1
after = after.replace(marker, '''/* MiCode enables the alternate HDD scheme only on M2/M3/N11.
 * N81A/sheng advertises zero; the HyperOS USB HAL reads this capability. */
static int sheng_enable_msflag_show(struct seq_file *seq, void *unused)
{
	seq_puts(seq, "0\\n");
	return 0;
}

'''+marker, 1)
old = '''	ret = eusb2_repeater_read_overrides(dev, "qcom,host-param-override-seq",
			&er->host_param_override_seq, &er->host_param_override_seq_cnt);
'''
assert after.count(old) == 1
after = after.replace(old, '''	/* Preserve the current binding and accept the stock 5.15 DT alias. */
	ret = eusb2_repeater_read_overrides(dev,
			of_find_property(dev->of_node, "qcom,host-param-override-seq", NULL) ?
			"qcom,host-param-override-seq" : "qcom,param-override-seq-host",
			&er->host_param_override_seq, &er->host_param_override_seq_cnt);
''', 1)
old = '\teusb2_repeater_create_debugfs(er);\n\treturn 0;'
assert after.count(old) == 1
after = after.replace(old, '''	eusb2_repeater_create_debugfs(er);
	/* Scope the stock ABI to the verified sheng model, not every Kalama DT. */
	{
		const char *model;

		if (!of_property_read_string(of_root, "model", &model) &&
		    !strcmp(model, "Qualcomm Technologies, Inc. 8550 sheng")) {
			er->sheng_ms_enable = proc_create_single("enable_msflag", 0444,
					NULL, sheng_enable_msflag_show);
			if (!er->sheng_ms_enable)
				dev_warn(dev, "failed to publish sheng USB capability\\n");
		}
	}
	return 0;''', 1)
old = '\tdebugfs_remove_recursive(er->root);\n\tusb_remove_repeater_dev(&er->ur);'
assert after.count(old) == 1
after = after.replace(old, '\tproc_remove(er->sheng_ms_enable);\n'+old, 1)
assert path.read_text() in (before, after), 'Unexpected local repeater edits'
refs = []
for name in ['lineage-kernel', 'micode-kernel']:
    root = ROOT/'src'/name
    source = root/relative
    text = source.read_text()
    refs.append(dict(repository=name, commit=subprocess.check_output(
        ['git', '-C', root, 'rev-parse', 'HEAD'], text=True).strip(), file=relative,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        stock_capability_present='enable_msflag' in text))
stock = (ROOT/'src/micode-kernel'/relative).read_text()
assert 'er->en_ms_flag = 0;' in stock and 'HARDWARE_PROJECT_N11' in stock
assert 'qcom,param-override-seq-host' in stock
path.write_text(after)
(PROJECT/'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-usb-hyperos.patch').write_text(
    ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                               fromfile='a/'+relative, tofile='b/'+relative)))
report = dict(files={'soc/'+relative:dict(before=hashlib.sha256(before.encode()).hexdigest(),
                                        after=hashlib.sha256(after.encode()).hexdigest())},
    references=refs, capability_value=0, capability_read_only=True,
    scope_model='Qualcomm Technologies, Inc. 8550 sheng',
    cause='HyperOS USB HAL repeatedly reads absent enable_msflag; old host override DT property was ignored',
    device_mode_tuning_changed=False, enumeration_root_cause_proven=False, hardware_result='pending')
(PROJECT/'reports/kernel618-usb-hyperos-source.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
