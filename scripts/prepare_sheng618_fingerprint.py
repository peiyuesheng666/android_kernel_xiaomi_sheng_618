#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage the sheng FPC electrical driver and Xiaomi fingerdown ABI for 6.18."""
import difflib
import hashlib
import json
import subprocess
from build_sheng618_upstream import ROOT, K618, PROJECT

source = ROOT / 'src/micode-kernel'
stage = K618 / 'sheng-ports/fingerprint'
revision = subprocess.check_output(['git', '-C', source, 'rev-parse', 'HEAD'], text=True).strip()
stage.mkdir(parents=True, exist_ok=True)
files = {}
patch = []


def once(text, old, new):
    assert text.count(old) == 1, old[:100]
    return text.replace(old, new, 1)


for name, relative in [('fpc1020_tee.c', 'fpc_1553/fpc1020_tee.c'),
                        ('xiaomi_fingerprint.c', 'xiaomi_fp/xiaomi_fingerprint.c')]:
    original = (source / 'drivers/input/fingerprint' / relative).read_text()
    text = original
    text = text.replace('#include <linux/pinctrl/qcom-pinctrl.h>', '#include <linux/pinctrl/consumer.h>\n#include <drm/drm_panel.h>')
    # These GPIOs are explicitly acquired/released by the vendor HAL protocol.
    # The removed devm_gpio_free interface must not be emulated with a no-op.
    text = text.replace('devm_gpio_request(dev,', 'gpio_request(')
    text = text.replace('devm_gpio_free(dev,', 'gpio_free(')
    text = text.replace('static retry_count = 0;', 'static int retry_count;')
    # The selected notifier already reserves this unused primary fingerprint slot.
    # Reuse its enum value instead of extending a shared ABI and rebuilding all clients.
    text = text.replace('PANEL_EVENT_NOTIFIER_CLIENT_FINGERPRINT,',
                        'PANEL_EVENT_NOTIFIER_CLIENT_PRIMARY_ONSCREENFINGERPRINT,')
    if name == 'fpc1020_tee.c':
        # Only publish a GPIO after ownership was acquired; failure cleanup must
        # never free another driver's GPIO. Preserve the real deferred errno.
        text = once(text, 'return FPC_GPIO_NO_DEFINED;', 'return rc;')
        text = once(text, '\t*gpio = rc;\n\n\trc = gpio_request( *gpio, label);',
                    '\t{\n\t\tint requested = rc;\n\t\trc = gpio_request(requested, label);\n\t\tif (!rc)\n\t\t\t*gpio = requested;\n\t}')
        text = once(text, 'return FPC_GPIO_REQUEST_FAIL;', 'return rc;')
        # The vendor bridge work callback is commented out in the published
        # sheng source. Its work_struct is never initialized; the IRQ already
        # notifies the stock HAL through the real sysfs interrupt endpoint.
        text = once(text, '\t\tschedule_work(&fpc1020->work);',
                    '\t\t/* No legacy bridge work: the HAL receives the IRQ above. */')
        text = once(text, '\tfpc1020->gpios_requested = false;\n\tdevice_init_wakeup(dev, 1);',
                    '\tfpc1020->gpios_requested = false;\n\t/* Enabled only after probe resources are ready. */')
        text = once(text, '\tfpc1020->ttw_wl = wakeup_source_register(dev, "fpc_ttw_wl");',
                    '\tfpc1020->ttw_wl = wakeup_source_register(dev, "fpc_ttw_wl");\n\tif (!fpc1020->ttw_wl)\n\t\treturn -ENOMEM;')
        text = once(text, '\t\tdev_err(dev, "fpc could not create sysfs\\n");\n\t\tgoto exit;',
                    '\t\tdev_err(dev, "fpc could not create sysfs\\n");\n\t\twakeup_source_unregister(fpc1020->ttw_wl);\n\t\tgoto exit;')
        text = once(text, '\tdev_info(dev, "%s: ok\\n", __func__);',
                    '\tdevice_init_wakeup(dev, true);\n\tdev_info(dev, "%s: ok\\n", __func__);')
        text = once(text, '\terror = fpc_check_panel(node);', '\terror = fpc_check_panel(node);\n\tof_node_put(node);')
        text = once(text, 'if (active_panel && !IS_ERR(cookie))', 'if (active_panel && !IS_ERR_OR_NULL(cookie))')
        text = once(text, '            if (vreg == NULL) {', '            if (IS_ERR(vreg)) {\n                rc = PTR_ERR(vreg);\n                vreg = NULL;')
        text = once(text, '            vreg = regulator_get(dev, "fp_vdd_vreg");',
                    '            if (!vreg)\n                vreg = devm_regulator_get(dev, "fp_vdd_vreg");')
        text = once(text, '                    regulator_put(vreg);\n                    vreg = NULL;',
                    '                    /* devm releases this acquired handle on detach. */')
        # Reject control requests before the HAL selected/acquired its supply.
        text = once(text, '    enabled = regulator_is_enabled(vreg);\n    mutex_unlock',
                    '    enabled = vreg ? regulator_is_enabled(vreg) : -ENODEV;\n    mutex_unlock')
        text = once(text, '    if (!strncmp(buf, "enable", strlen("enable"))) {',
                    '    if (!vreg) {\n        mutex_unlock(&fpc1020->lock);\n        return -ENODEV;\n    }\n    if (!strncmp(buf, "enable", strlen("enable"))) {')
        text = once(text, '\t\tpower_reset();',
                    '\t\tif (!vreg) {\n\t\t\tmutex_unlock(&fpc1020->lock);\n\t\t\treturn -ENODEV;\n\t\t}\n\t\tpower_reset();')
        text = once(text, 'static int fpc1020_remove(struct platform_device *pdev)',
                    'static void fpc1020_remove(struct platform_device *pdev)')
        a = text.index('static void fpc1020_remove(')
        b = text.index('\n}\n', a)
        body = text[a:b]
        body = once(body, '\treturn 0;', '\treturn;')
        body = once(body, '\tmutex_destroy(&fpc1020->lock);',
                    '\t(void)device_prepare(fpc1020, false);\n\t(void)request_vreg_gpio(fpc1020, false);\n\tdevice_init_wakeup(&pdev->dev, false);\n\tvreg = NULL;\n\tcookie = NULL;\n\tactive_panel = NULL;\n\tmutex_destroy(&fpc1020->lock);')
        text = text[:a] + body + text[b:]
    else:
        text = once(text, 'static int xiaomi_fp_remove(struct platform_device *pdev)',
                    'static void xiaomi_fp_remove(struct platform_device *pdev)')
        a = text.index('static void xiaomi_fp_remove(')
        b = text.index('\n}\n', a)
        body = once(text[a:b], '\treturn 0;', '\treturn;')
        text = text[:a] + body + text[b:]
    (stage / name).write_text(text)
    files[name] = dict(original=hashlib.sha256(original.encode()).hexdigest(),
                      staged_sha256=hashlib.sha256(text.encode()).hexdigest(), source=relative)
    patch.extend(difflib.unified_diff(original.splitlines(True), text.splitlines(True),
                 fromfile='a/'+relative, tofile='b/'+relative))
kbuild = '''# SPDX-License-Identifier: GPL-2.0-only
ccflags-y += -include $(src)/../../tp-autoconf.h
ccflags-y += -I$(src)/../../soc/include -I$(src)/../../vendor/qcom/opensource/display-drivers/include
obj-m += fpc1552.o xiaomifp.o
fpc1552-y := fpc1020_tee.o
xiaomifp-y := xiaomi_fingerprint.o
'''
(stage / 'Kbuild').write_text(kbuild)
files['Kbuild'] = dict(staged_sha256=hashlib.sha256(kbuild.encode()).hexdigest())
(PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/fingerprint-fpc.patch').write_text(''.join(patch))
(PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/fingerprint.Kbuild').write_text(kbuild)
(PROJECT / 'reports/kernel618-fingerprint-source.json').write_text(json.dumps(dict(
    repository='https://github.com/MiCode/Xiaomi_Kernel_OpenSource', revision=revision,
    files=files, stage=str(stage),
    applicability='Original sheng fpc,fpc1020 and xiaomi-fingerprint nodes; side-mounted FPC, not phone in-display FOD',
    alternatives='Selected SM8550 integration and local LOS sources lack this sheng FPC platform implementation',
    preserved='Original sysfs request/power/IRQ interface and pinctrl names; biometric matching and enrolled data stay in stock HAL/TEE',
    adaptations='6.18 platform remove and GPIO API, typed retry counter, OF reference and regulator error checks',
    hardware_result='pending'), indent=2)+'\n')
print('Staged sheng FPC and fingerdown drivers')
