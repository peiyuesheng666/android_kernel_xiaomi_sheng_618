#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Report an already-live replacement before rejecting a legacy duplicate's layout.

Do not execute old code, bypass module authentication, or report missing drivers loaded.
Android libmodprobe treats EEXIST as the normal successful duplicate case.
"""
import difflib
import hashlib
import json
from build_sheng618_upstream import ACK, PROJECT

path = ACK / 'kernel/module/main.c'
receipt = PROJECT / 'reports/kernel618-module-reuse-source.json'
old = '''	err = elf_validity_cache_index_info(info);
	if (err < 0)
		return err;
	err = elf_validity_cache_index_mod(info);'''
new = '''	err = elf_validity_cache_index_info(info);
	if (err < 0)
		return err;
#ifdef CONFIG_SHENG_LEGACY_MODULE_REUSE
	/* Stock HyperOS tries its 5.15 files after the embedded 6.18 layer.
	 * Preserve the native duplicate result without interpreting old struct
	 * module data. ELF bounds and authentication have already been checked.
	 * A missing/not-live replacement still follows every normal ABI check.
	 */
	if (info->name && strstarts(get_modinfo(info, "vermagic") ?: "", "5.15.")) {
		struct module *loaded;
		bool live;

		mutex_lock(&module_mutex);
		loaded = find_module(info->name);
		live = loaded && loaded->state == MODULE_STATE_LIVE;
		mutex_unlock(&module_mutex);
		if (live) {
			pr_notice("sheng_module_reuse: %s already live; legacy duplicate -> EEXIST\\n",
				  info->name);
			return -EEXIST;
		}
	}
#endif
	err = elf_validity_cache_index_mod(info);'''
before = path.read_text()
if receipt.exists() and hashlib.sha256(before.encode()).hexdigest() == json.loads(receipt.read_text())['after']:
    assert before.count(new) == 1
    before = before.replace(new, old, 1)
assert before.count(old) == 1
after = before.replace(old, new, 1)
path.write_text(after)
patch = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                 fromfile='a/kernel/module/main.c', tofile='b/kernel/module/main.c', n=0))
(PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/legacy-module-reuse.patch').write_text(patch)
kconfig = ACK / 'kernel/module/Kconfig'
entry = '\nconfig SHENG_LEGACY_MODULE_REUSE\n\tbool "Sheng legacy duplicate module recognition"\n\tdepends on MODULES\n'
if 'config SHENG_LEGACY_MODULE_REUSE\n' not in kconfig.read_text():
    with kconfig.open('a') as stream:
        stream.write(entry)
receipt.write_text(json.dumps(dict(before=hashlib.sha256(before.encode()).hexdigest(),
    after=hashlib.sha256(after.encode()).hexdigest(),
    trigger='r12 init.qti.kernel.rc:54 waits vendor.all.modules.ready; both stock modprobe services exit 1 after 5.15 module-layout rejection',
    evidence='msm_sysstats replacement loaded at 4.191 s; stock duplicate refused at 31.411 s. zsmalloc replacement also live before GKI duplicate.',
    behavior='Only 5.15 modinfo names with a MODULE_STATE_LIVE counterpart return native EEXIST before old struct layout; missing modules remain errors',
    references=[dict(commit='c3956156ce7c4193c451dfda531fad72d35bfebb',
                     path='kernel-6.18/k618_insmod.c', result='Selected upstream uses generic kretprobe failure tolerance; do not enable it because it also masks absent drivers'),
                dict(commit='ff4a6c3bb0f471a9dd186293a47b62c83829b97d', path='kernel/module/main.c',
                     result='ELF section/name validation runs before struct layout; module_mutex and MODULE_STATE_LIVE protect the duplicate check'),
                dict(path='/root/sheng-lineage/firmware-dump/partitions/vendor/bin/vendor_modprobe.sh',
                     result='First-module failure aborts before setprop vendor.all.modules.ready'),
                dict(commit='65d661b1a536701e8b118be4e9728d7b5ca727c9',
                     path='/root/sheng-lineage/lineage-24.0/system/core/libmodprobe/libmodprobe_ext.cpp',
                     result='AOSP Modprobe::Insmod accepts EEXIST as an already loaded module')],
    scope='Kernel-only opt-in HyperOS duplicate recognition; no changes to firmware or vendor scripts'), indent=2) + '\n')
