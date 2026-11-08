#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual extracted AUX lifecycle routines with real DRM/I2C registration.

Only transfer callbacks and one requested registration failure are synthetic.
The test lives in QEMU's disposable initrd, never the delivery module overlay.
"""
import hashlib
import json
import re
import subprocess
import sys

from build_sheng618_upstream import ACK, K618, OUT, PROJECT, ROOT, environment

tree = K618 / 'vendor/qcom/opensource/display-drivers'
folder = ROOT / 'diagnostic/aux-r12/aux-lifetime-test'
folder.mkdir(parents=True, exist_ok=True)
source = (tree / 'msm/dp/dp_aux.c').read_text()
header = (tree / 'msm/dp/dp_aux.h').read_text()
bridge = (tree / 'msm/dp/dp_aux_bridge.h').read_text()
devres = (ACK / 'drivers/base/devres.c').read_text()

def block(text, start, struct=False):
    pos = text.index(start)
    opening = text.index('{', pos)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[pos:end + int(struct)] + '\n'

register = block(source, 'static int dp_aux_register(')
deregister = block(source, 'static void dp_aux_deregister(')
put = block(source, 'void dp_aux_put(')
assert 'dp_aux_deregister(dp_aux);' in put and 'dp_aux->drm_aux = NULL;' in deregister
old_put = put.replace('dp_aux_put(', 'dp_aux_put_before_fix(', 1).replace(
    '\t/* Includes post-init failures after AUX registration (e.g. PLL). */\n'
    '\tdp_aux_deregister(dp_aux);\n', '')
definitions = '\n'.join([
    block(header, 'struct dp_aux {', True),
    block(bridge, 'struct dp_aux_bridge {', True),
    block(source, 'struct dp_aux_private {', True),
    block(devres, 'struct devres_node {', True),
    block(devres, 'struct devres {', True)])
c = r'''// SPDX-License-Identifier: GPL-2.0-only
#include <linux/module.h>
#include <linux/version.h>
#include <linux/device.h>
#include <linux/slab.h>
#include <linux/completion.h>
#include <linux/notifier.h>
#include <drm/display/drm_dp_helper.h>
#include <drm/drm_device.h>
#include <drm/drm_drv.h>
struct dp_aux_cfg;
struct dp_catalog_aux;
struct dp_aux_bridge;
#define DP_AUX_ERR(aux, fmt, ...) pr_err(fmt, ##__VA_ARGS__)
'''
c += definitions
c += r'''
/* Match the stale devices-kset entry proved by both r10 and r11. */
static_assert(offsetof(struct dp_aux_private, drm_aux.ddc.dev.kobj.entry) == 352);
static_assert(offsetof(struct devres, data) == 128);
static_assert(offsetof(struct devres, data) +
              offsetof(struct dp_aux_private, drm_aux.ddc.dev.kobj.entry) == 480);
static unsigned int unregisters, frees, live_at_free;
static bool fail_register;
static int wrap_register(struct drm_dp_aux *aux)
{
    if (fail_register)
        return -EIO;
    return drm_dp_aux_register(aux);
}
static void wrap_unregister(struct drm_dp_aux *aux)
{
    unregisters++;
    drm_dp_aux_unregister(aux);
}
static void wrap_free(struct device *dev, void *ptr)
{
    struct dp_aux_private *aux = ptr;
    frees++;
    if (aux->dp_aux.drm_aux) {
        /* A broken version is detected without freeing a live I2C device. */
        live_at_free++;
        drm_dp_aux_unregister(&aux->drm_aux);
    }
    devm_kfree(dev, ptr);
}
static ssize_t dp_aux_transfer(struct drm_dp_aux *aux, struct drm_dp_aux_msg *msg)
{
    return -EIO;
}
static ssize_t dp_aux_bridge_transfer(struct drm_dp_aux *aux, struct drm_dp_aux_msg *msg)
{
    return -EIO;
}
#define drm_dp_aux_register wrap_register
#define drm_dp_aux_unregister wrap_unregister
#define devm_kfree wrap_free
void dp_aux_put(struct dp_aux *dp_aux);
void dp_aux_put_before_fix(struct dp_aux *dp_aux);
'''
c += register + deregister + put + old_put
c += r'''
#undef drm_dp_aux_register
#undef drm_dp_aux_unregister
#undef devm_kfree
static const struct drm_driver test_driver = {
    .name = "sheng-aux-lifetime", .desc = "QEMU AUX lifecycle regression",
    .major = 1,
};
static int __init sheng_aux_test_init(void)
{
    struct device *dev = root_device_register("sheng-aux-lifetime");
    struct drm_device *drm;
    int rc = 0, mode;
    if (IS_ERR(dev))
        return PTR_ERR(dev);
    drm = drm_dev_alloc(&test_driver, dev);
    if (IS_ERR(drm)) {
        rc = PTR_ERR(drm);
        goto out_dev;
    }
    for (mode = 0; mode < 7; mode++) {
        struct dp_aux_private *aux = devm_kzalloc(dev, sizeof(*aux), GFP_KERNEL);
        unsigned int expected = mode == 2 || mode == 3 ? 0 : mode == 4 ? 2 : 1;
        int registered = 0;
        if (!aux) {
            rc = -ENOMEM;
            break;
        }
        aux->dev = dev;
        mutex_init(&aux->mutex);
        unregisters = frees = live_at_free = 0;
        fail_register = mode == 2;
        if (mode != 3) {
            registered = dp_aux_register(&aux->dp_aux, drm);
            if (registered != (fail_register ? -EIO : 0))
                rc = -EINVAL;
        }
        if (!registered && (mode == 1 || mode == 4 || mode == 5))
            dp_aux_deregister(&aux->dp_aux);
        if (mode == 1 || mode == 5)
            dp_aux_deregister(&aux->dp_aux);
        if (mode == 4 && dp_aux_register(&aux->dp_aux, drm))
            rc = -EINVAL;
        if (mode == 6)
            dp_aux_put_before_fix(&aux->dp_aux);
        else
            dp_aux_put(&aux->dp_aux);
        if (mode == 6 ? (unregisters || frees != 1 || live_at_free != 1) :
                       (unregisters != expected || frees != 1 || live_at_free))
            rc = -EINVAL;
        pr_notice("SHENG_AUX_CASE mode=%d unregisters=%u frees=%u live_at_free=%u rc=%d\n",
                  mode, unregisters, frees, live_at_free, rc);
        if (rc)
            break;
    }
    if (!rc) {
        pr_notice("SHENG_AUX_OLD_BUG_REPRODUCED: freed with live registered adapter; test wrapper removed it safely\n");
        pr_notice("SHENG_AUX_LIFETIME_PASS: 6 fixed cases; real I2C AUX; devres128+entry352=480\n");
    }
    drm_dev_put(drm);
out_dev:
    root_device_unregister(dev);
    return rc;
}
module_init(sheng_aux_test_init);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Disposable test of extracted Qualcomm AUX lifecycle functions");
'''
test_source = folder / 'sheng_aux_test.c'
test_source.write_text(c)
(folder / 'Makefile').write_text('obj-m := sheng_aux_test.o\n')
with (folder / 'build.log').open('w') as stream:
    subprocess.run(['make', '-C', str(ACK), 'O=' + str(OUT), 'ARCH=arm64', 'LLVM=1',
                    'LLVM_IAS=1', 'M=' + str(folder), '-j8', 'modules'],
                   env=environment(8), stdout=stream, stderr=subprocess.STDOUT, check=True)
subprocess.run([sys.executable, PROJECT / 'scripts/test_sheng618_disklog.py', '--revision',
                'aux-r12', '--helper-exec', '--positive-only', '--extra-test-module',
                folder / 'sheng_aux_test.ko', '--require-marker', 'SHENG_AUX_LIFETIME_PASS'], check=True)
report = dict(source_file=str(tree / 'msm/dp/dp_aux.c'),
    source_sha256=hashlib.sha256(source.encode()).hexdigest(),
    extracted_functions=['dp_aux_register', 'dp_aux_deregister', 'dp_aux_put'],
    exact_private_public_and_bridge_structs_extracted=True,
    compiled_aux_i2c_device_kobject_entry_offset=352,
    compiled_devres_data_offset=128, combined_slab_pointer_offset=480,
    actual_drm_and_i2c_registration=True,
    hardware_transfer_callbacks_stubbed=True, one_registration_failure_injected=True,
    free_wrapper_detects_and_safely_unregisters_a_live_adapter_before_free=True,
    cases=['registered then put (PLL failure)', 'deregister twice then put',
           'registration failure then put', 'never registered then put',
           'register-deregister-register then put', 'normal unbind then put'],
    all_cases_passed=True, test_module_only_in_disposable_qemu_initrd=True,
    before_fix_live_adapter_at_free_detected=True,
    hardware_dp_or_display_tested=False,
    qemu_receipt='kernel618-aux-r12-qemu-regression.json')
(PROJECT / 'reports/kernel618-dp-aux-lifetime-test.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
