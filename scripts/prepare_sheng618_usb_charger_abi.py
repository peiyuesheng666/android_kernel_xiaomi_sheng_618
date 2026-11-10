#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restore three shipping sheng Type-C class attributes, without forcing roles."""
import difflib
import hashlib
import json
import re
import subprocess

from build_sheng618_upstream import K618, PROJECT, ROOT

relative = 'soc/drivers/power/supply/qti_battery_charger.c'
path = K618 / relative
backup = ROOT / 'diagnostic/hardware-r38/charger-before.c'
backup.parent.mkdir(parents=True, exist_ok=True)
before = backup.read_text() if backup.exists() else path.read_text()
assert 'static ssize_t screen_cctog_show' not in before
disassembly = PROJECT / 'reports/device/kernel618-hardware-r37/stock-charger-disassembly.txt'
stock = disassembly.read_text()
contracts = {'screen_cctog': ('XM_PROP_SCREEN_CCTOG', 46, 'bool'),
             'cc_toggle': ('XM_PROP_CC_TOGGLE', 111, 'int'),
             'otg_ui_support': ('XM_PROP_OTG_UI_SUPPORT', 109, None)}
checked = {}
functions = []
for name, (prop, number, parser) in contracts.items():
    assert re.search(r'\b' + prop + r'\s*=\s*' + str(number) + r'\s*,', before)
    operations = ('show', 'store') if parser else ('show',)
    evidence = {}
    for operation in operations:
        match = re.search(r'^([0-9a-f]{16}) <' + name + '_' + operation + r'\.[0-9a-f]{32}>:\n(.*?)(?=\n[0-9a-f]{16} <|\Z)', stock, re.M | re.S)
        assert match, (name, operation)
        body = match[2]
        assert '#0x' + format(number, 'x') + '00000000' in body, (name, operation)
        if operation == 'store':
            assert ('kstrtobool' if parser == 'bool' else 'kstrtoint') in body
        evidence[operation] = '0x' + match[1]
    checked[name] = dict(property=prop, id=number, parser=parser,
                         stock_functions=evidence, read_only=parser is None)
    functions.append(f'''static ssize_t {name}_show(const struct class *c,
\t\tconst struct class_attribute *attr, char *buf)
{{
\tstruct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev,
\t\t\t\t\t\tbattery_class);
\tstruct psy_state *pst = &bcdev->psy_list[PSY_TYPE_XM];
\tint rc;

\trc = read_property_id(bcdev, pst, {prop});
\tif (rc < 0)
\t\treturn rc;
\treturn scnprintf(buf, PAGE_SIZE, "%u", pst->prop[{prop}]);
}}

''')
    if parser:
        declaration = 'bool val;' if parser == 'bool' else 'int val;'
        parse = 'kstrtobool(buf, &val)' if parser == 'bool' else 'kstrtoint(buf, 10, &val)'
        functions.append(f'''static ssize_t {name}_store(const struct class *c,
\t\tconst struct class_attribute *attr, const char *buf, size_t count)
{{
\tstruct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev,
\t\t\t\t\t\tbattery_class);
\t{declaration}
\tint rc;

\tif ({parse})
\t\treturn -EINVAL;
\trc = write_property_id(bcdev, &bcdev->psy_list[PSY_TYPE_XM],
\t\t\t\t{prop}, val);
\tif (rc < 0)
\t\treturn rc;
\treturn count;
}}

''')
    functions.append(f'static CLASS_ATTR_{"RW" if parser else "RO"}({name});\n\n')
helper = '''/* HyperOS controls CC detection through these shipping class attributes.
 * Keep its bool/int parsing and remote error handling. Do not invent a
 * startup role, write a default, or disable firmware protections.
 */
''' + ''.join(functions) + '''static int sheng_battery_chg_add_usb_attributes(struct battery_chg_dev *bcdev)
{
\tint rc;

\tif (!of_root || of_property_match_string(of_root, "model",
\t\t\t"Qualcomm Technologies, Inc. 8550 sheng") < 0)
\t\treturn 0;

\trc = class_create_file(&bcdev->battery_class, &class_attr_screen_cctog);
\tif (rc)
\t\treturn rc;
\trc = class_create_file(&bcdev->battery_class, &class_attr_cc_toggle);
\tif (rc)
\t\tgoto remove_screen;
\trc = class_create_file(&bcdev->battery_class, &class_attr_otg_ui_support);
\tif (rc)
\t\tgoto remove_toggle;
\treturn 0;

remove_toggle:
\tclass_remove_file(&bcdev->battery_class, &class_attr_cc_toggle);
remove_screen:
\tclass_remove_file(&bcdev->battery_class, &class_attr_screen_cctog);
\treturn rc;
}

'''
marker = 'static struct attribute *battery_class_attrs[] = {\n'
assert before.count(marker) == 1
after = before.replace(marker, helper + marker, 1)
marker = '''\t\tdev_err(dev, "Failed to create battery_class rc=%d\\n", rc);
\t\tgoto error;
\t}
'''
assert after.count(marker) == 1
after = after.replace(marker, marker + '''
\trc = sheng_battery_chg_add_usb_attributes(bcdev);
\tif (rc) {
\t\tclass_unregister(&bcdev->battery_class);
\t\tdev_err(dev, "Failed to create sheng USB attributes rc=%d\\n", rc);
\t\tgoto error;
\t}
''', 1)
assert path.read_text() in (before, after), 'Unexpected charger changes'
if not backup.exists():
    backup.write_text(before)
path.write_text(after)
patch = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/sheng-usb-charger-abi.patch'
patch.write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                          fromfile='a/' + relative, tofile='b/' + relative)))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
references = []
for name in ('lineage-kernel', 'micode-kernel', 'lineage-devicetrees'):
    root = ROOT / 'src' / name
    references.append(dict(repository=name, commit=subprocess.check_output(
        ['git', '-C', root, 'rev-parse', 'HEAD'], text=True).strip()))
piano = '/root/sheng-source-inputs/reference/piano-device'
references.append(dict(repository='LineageOS-piano', commit=subprocess.check_output(
    ['git', '-C', piano, 'rev-parse', 'HEAD'], text=True).strip(),
    applicability='Reviewed rootdir USB recovery/Type-C permissions; no sheng XM class-control recipe. Its recovery peripheral override does not apply to normal HyperOS startup.'))
report = dict(revision='hardware-r38', date='2026-11-09',
    files={relative: dict(before=sha(backup), after=sha(path))},
    patch_sha256=sha(patch), stock_disassembly_sha256=sha(disassembly),
    scope_model='Qualcomm Technologies, Inc. 8550 sheng', contracts=checked,
    references=references,
    applicability='MiCode sheng implements cc_toggle and otg_ui_support; LOS nuwa generic charger has no sheng XM controls. Actual shipping module supplies screen_cctog with bool parsing.',
    evidence='r37: absent nodes read back; stock init writes screen_cctog at 47.117 and 50.141 seconds fail. micharge init expects cc_toggle and otg_ui_support.',
    default_property_writes_added=False, firmware_protections_changed=False,
    root_components_added=False, usb_fixed=False, build_result='pending', hardware_result='pending',
    limitation='Repairs a proven missing userspace/firmware contract. Does not prove the cause of delayed USB recognition.')
(PROJECT / 'reports/kernel618-usb-charger-abi-source.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
