#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual new callbacks and partial-registration rollback on host."""
import json
import subprocess

from build_sheng618_upstream import K618, PROJECT, ROOT
from sheng618_usb_charger_abi import verify

source = (K618 / 'soc/drivers/power/supply/qti_battery_charger.c').read_text()
callbacks = source.split('static ssize_t screen_cctog_show', 1)[1].split(
    'static struct attribute *battery_class_attrs[]', 1)[0]
callbacks = 'static ssize_t screen_cctog_show' + callbacks
work = ROOT / 'diagnostic/hardware-r38/charger-callback-check'
work.mkdir(parents=True, exist_ok=True)
harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#define PAGE_SIZE 4096
#define container_of(ptr, type, member) ((type *)((char *)(ptr) - offsetof(type, member)))
#define scnprintf snprintf
#define XM_PROP_SCREEN_CCTOG 46
#define XM_PROP_CC_TOGGLE 111
#define XM_PROP_OTG_UI_SUPPORT 109
#define PSY_TYPE_XM 0
struct class { int unused; };
struct class_attribute { int slot; };
struct psy_state { unsigned int prop[222]; };
struct battery_chg_dev { int prefix; struct class battery_class; struct psy_state psy_list[1]; };
static int result, last_prop, last_value, active, attempt, fail_at, match_result;
static void *of_root = (void *)1;
#define CLASS_ATTR_RW(name) struct class_attribute class_attr_##name = { __LINE__ }
#define CLASS_ATTR_RO(name) CLASS_ATTR_RW(name)
static int kstrtobool(const char *buf, bool *v) {
    if (!strcmp(buf, "1") || !strcmp(buf, "true")) *v = true;
    else if (!strcmp(buf, "0") || !strcmp(buf, "false")) *v = false;
    else return -EINVAL;
    return 0;
}
static int kstrtoint(const char *buf, int base, int *v) {
    char *end; long value = strtol(buf, &end, base);
    if (end == buf || *end || value > 2147483647L || value < -2147483648L) return -EINVAL;
    *v = value; return 0;
}
static int read_property_id(struct battery_chg_dev *b, struct psy_state *p, int id) {
    last_prop = id; return result;
}
static int write_property_id(struct battery_chg_dev *b, struct psy_state *p, int id, int value) {
    last_prop = id; last_value = value; return result;
}
static int of_property_match_string(void *root, const char *name, const char *value) {
    assert(!strcmp(name, "model"));
    assert(!strcmp(value, "Qualcomm Technologies, Inc. 8550 sheng"));
    return match_result;
}
static int class_create_file(struct class *c, struct class_attribute *a) {
    ++attempt;
    if (attempt == fail_at) return -ENOMEM;
    ++active; return 0;
}
static void class_remove_file(struct class *c, struct class_attribute *a) {
    assert(active > 0); --active;
}
'''
main = r'''
int main(void) {
    struct battery_chg_dev b = {0}; char out[PAGE_SIZE];
    b.psy_list[0].prop[46] = 1; b.psy_list[0].prop[111] = 2; b.psy_list[0].prop[109] = 1;
    assert(screen_cctog_store(&b.battery_class, NULL, "true", 4) == 4);
    assert(last_prop == 46 && last_value == 1);
    assert(screen_cctog_store(&b.battery_class, NULL, "false", 5) == 5 && last_value == 0);
    assert(screen_cctog_store(&b.battery_class, NULL, "bad", 3) == -EINVAL);
    assert(cc_toggle_store(&b.battery_class, NULL, "2", 1) == 1);
    assert(last_prop == 111 && last_value == 2);
    assert(cc_toggle_store(&b.battery_class, NULL, "invalid", 7) == -EINVAL);
    assert(cc_toggle_store(&b.battery_class, NULL, "2147483648", 10) == -EINVAL);
    assert(screen_cctog_show(&b.battery_class, NULL, out) == 1 && !strcmp(out, "1") && last_prop == 46);
    assert(cc_toggle_show(&b.battery_class, NULL, out) == 1 && !strcmp(out, "2") && last_prop == 111);
    assert(otg_ui_support_show(&b.battery_class, NULL, out) == 1 && !strcmp(out, "1") && last_prop == 109);
    result = -ETIMEDOUT;
    assert(screen_cctog_store(&b.battery_class, NULL, "1", 1) == result);
    assert(cc_toggle_store(&b.battery_class, NULL, "0", 1) == result);
    assert(screen_cctog_show(&b.battery_class, NULL, out) == result);
    assert(cc_toggle_show(&b.battery_class, NULL, out) == result);
    assert(otg_ui_support_show(&b.battery_class, NULL, out) == result);
    result = 0;
    match_result = -1;
    assert(sheng_battery_chg_add_usb_attributes(&b) == 0 && attempt == 0);
    match_result = 0; of_root = NULL;
    assert(sheng_battery_chg_add_usb_attributes(&b) == 0 && attempt == 0);
    of_root = (void *)1;
    for (fail_at = 1; fail_at <= 3; ++fail_at) {
        attempt = active = 0;
        assert(sheng_battery_chg_add_usb_attributes(&b) == -ENOMEM && active == 0);
    }
    fail_at = attempt = active = 0;
    assert(sheng_battery_chg_add_usb_attributes(&b) == 0 && active == 3 && attempt == 3);
    puts("callbacks, property routing, remote failures, model scoping and partial-registration rollback passed");
    return 0;
}
'''
(work / 'check.c').write_text(harness + callbacks + main)
subprocess.run(['cc', '-Wall', '-Wextra', '-Wno-unused-parameter', '-Werror',
                '-o', work / 'check', work / 'check.c'], check=True)
subprocess.run([work / 'check'], check=True)
new = verify(K618 / 'soc/qti_battery_charger.ko', PROJECT, K618)
old = ROOT / 'diagnostic/hardware-r37/layer/lib/modules/qti_battery_charger.ko'
try:
    verify(old, PROJECT, K618)
except ValueError as error:
    rejected = str(error)
else:
    raise AssertionError('Old r37 charger payload accepted')
report = dict(actual_callback_source_tested=True,
              checks=['bool/int parsing', 'exact property IDs', 'remote error propagation',
                      'other models skipped', 'all three partial-registration failures rolled back'],
              target_elf=new, known_old_r37_rejected=rejected,
              hardware_verified=False)
(PROJECT / 'reports/kernel618-usb-charger-abi-validation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
