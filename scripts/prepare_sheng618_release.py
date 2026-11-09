#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Remove installed investigation hooks while retaining the tested hardware fixes."""
import difflib
import hashlib
import json
import re
from build_sheng618_upstream import ACK, K618, PROJECT, ROOT


def end_group(text, start, opening='(', closing=')'):
    """Find a C group end, ignoring comments and string/character literals."""
    depth, pos = 0, start
    token = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[\s\S]', re.S)
    for match in token.finditer(text, start):
        item = match.group()
        if item == opening:
            depth += 1
        elif item == closing:
            depth -= 1
            if not depth:
                return match.end()
    raise AssertionError('Unbalanced C group at ' + str(pos))


def stub(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    end = end_group(text, brace, '{', '}')
    return text[:brace] + '{\n\t/* Release: investigation disabled. */\n}' + text[end:]


def remove_calls(text, predicate):
    pattern = re.compile(r'\b(?:pr_(?:info|notice|emerg)|dev_(?:info|notice)|printk)\s*\(')
    spans = []
    for match in pattern.finditer(text):
        end = end_group(text, text.index('(', match.start()))
        call = text[match.start():end]
        if predicate(call):
            spans.append((match.start(), end))
    for start, end in reversed(spans):
        text = text[:start] + 'do { } while (0)' + text[end:]
    return text, len(spans)


changes = {}


def edit(path, transform):
    before = path.read_text()
    after = transform(before)
    if before == after:
        return
    relative = path.relative_to(K618).as_posix()
    changes[relative] = dict(before_sha256=hashlib.sha256(before.encode()).hexdigest(),
                             after_sha256=hashlib.sha256(after.encode()).hexdigest())
    path.write_text(after)
    patches.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                    fromfile='a/' + relative, tofile='b/' + relative))


patches = []
smmu = K618 / 'soc/drivers/iommu/arm/arm-smmu/arm-smmu.c'


def smmu_release(text):
    if 'static unsigned int sheng_scan_watch_ms;' not in text:
        assert 'Release: no register sampling' in text
        return text
    start = text.index('/* No boot hold or register writes. Sample for at most three seconds,')
    end = text.index('\nvoid arm_smmu_write_context_bank', start)
    text = text[:start] + '''static inline void sheng_smmu_trace_streams(struct arm_smmu_device *smmu,
        const char *stage)
{
    /* Release: no register sampling or background watch. */
}
''' + text[end:]
    text = text.replace('\tcancel_delayed_work_sync(&sheng_scan_watch_work);\n', '')
    return remove_calls(text, lambda call: 'sheng ' in call)[0]


edit(smmu, smmu_release)


def dispcc_release(text):
    text = stub(text, 'static void sheng_dispcc_trace(')
    text = re.sub(r'static unsigned int sheng_postclock_hold_ms;\nmodule_param\([^\n]+\nMODULE_PARM_DESC\([^\n]+\n', '', text)
    text = text.replace('\tif (sheng_postclock_hold_ms > 10000)\n\t\treturn -EINVAL;\n', '')
    anchor = '\tif (!ret && sheng_dispcc_board() && sheng_postclock_hold_ms) {'
    if anchor in text:
        start = text.index(anchor)
        end = end_group(text, text.index('{', start), '{', '}')
        text = text[:start] + text[end:]
    return remove_calls(text, lambda call: 'sheng_dispcc:' in call)[0]


edit(K618 / 'soc/drivers/clk/qcom/dispcc-kalama.c', dispcc_release)
display = K618 / 'vendor/qcom/opensource/display-drivers/msm'


def display_entry(text):
    text = re.sub(r'(?:static )?unsigned int sheng_(?:probe_delay|before_display_hold)_ms;\nmodule_param\([^\n]+\nMODULE_PARM_DESC\([^\n]+\n', '', text)
    text = text.replace('\tif (sheng_before_display_hold_ms > 10000)\n\t\treturn -EINVAL;\n', '')
    anchor = '\tif (sheng_before_display_hold_ms) {'
    if anchor in text:
        start = text.index(anchor)
        end = end_group(text, text.index('{', start), '{', '}')
        text = text[:start] + text[end:]
    return text


edit(display / 'msm_drv.c', display_entry)
edit(display / 'sheng_boot_trace.h', lambda text: '''/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SHENG_BOOT_TRACE_H
#define SHENG_BOOT_TRACE_H
static inline void sheng_probe_pause(void) { }
static inline void sheng_probe_checkpoint(const char *stage) { }
#endif
''')
edit(display / 'sde/sde_hw_intf.c', lambda text: stub(text, 'void sheng_intf_handoff_trace('))
for path in display.rglob('*.c'):
    edit(path, lambda text: remove_calls(text, lambda call:
        any(marker in call for marker in ('sheng_', 'sheng ', 'k618:')))[0])
for path in (K618 / 'soc').rglob('sheng_early_scan_trace.h'):
    edit(path, lambda text: '''/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SHENG_EARLY_SCAN_TRACE_H
#define SHENG_EARLY_SCAN_TRACE_H
static inline void sheng_early_scan_trace(const char *stage) { }
#endif
''')
keyboard = K618 / 'sheng-ports/keyboard/sheng_nanosic.c'
edit(keyboard, lambda text: remove_calls(text, lambda call: True)[0])
for path in (ACK / 'kernel/module/main.c', ACK / 'fs/crypto/keyring.c'):
    edit(path, lambda text: remove_calls(text, lambda call: 'sheng_' in call)[0])
edit(K618 / 'soc/drivers/power/supply/qti_battery_charger.c',
     lambda text: remove_calls(text, lambda call: any(value in call for value in
        ('sheng_', 'k618:', 'register panel notifier successful')))[0])
edit(K618 / 'mark/k618_load.c', lambda text: remove_calls(text, lambda call:
    any(marker in call for marker in (': trying', ': loaded', ' modules from ', ': done:')))[0])

# These hooks must be absent, rather than merely disabled by a boot argument.
assert 'sheng_scan_watch_ms' not in smmu.read_text()
assert 'sheng_postclock_hold_ms' not in (K618 / 'soc/drivers/clk/qcom/dispcc-kalama.c').read_text()
assert 'sheng_before_display_hold_ms' not in (display / 'msm_drv.c').read_text()
assert 'sheng_probe_delay_ms' not in (display / 'msm_drv.c').read_text()
assert 'qti_set_keyboard_plugin(wanted)' in keyboard.read_text()
assert 'hid_destroy_device(nanosic->hid_keyboard)' in keyboard.read_text()
assert 'sheng_nano_disconnect_clients(nano)' in keyboard.read_text()
if changes:
    folder = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18'
    (folder / 'sheng-release-cleanup.patch').write_text(''.join(patches))
    (PROJECT / 'reports/kernel618-release-source.json').write_text(json.dumps(dict(
        changes=changes, hardware_fixes_retained=True, keyboard_disconnect_retained=True,
        display_priority_base='hardware-r69', logger_config='CONFIG_SHENG_BOOTLOG=n'), indent=2) + '\n')
print('Release sources prepared: ' + str(len(changes)) + ' files', flush=True)
