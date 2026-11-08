#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Port the stock sheng PS5169 to the selected 6.18 redriver callbacks."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from audit_kernel618_modules import ElfModule, check_candidate
from audit_sheng618_overlay import audit, entries
from build_sheng618_upstream import ACK, CLANG, K618, OUT, PROJECT, ROOT, environment

source = ROOT / 'src/micode-kernel'
commit = '29db5d592c5b577aa9d9611da988a5e071d100dd'
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip() == commit
stage = ROOT / 'ports/ps5169'
stage.mkdir(parents=True, exist_ok=True)
original = (source / 'drivers/usb/redriver/ps5169.c').read_text()
text = original


def replace(old, new):
    global text
    assert text.count(old) == 1, old
    text = text.replace(old, new, 1)


start = text.index('// gpio_get_value(info->cc_gpio)')
end = text.index('static int ps5169_get_chipid_revision', start)
text = text[:start] + '''/* Controller callbacks provide orientation; the board also wires a CC GPIO. */
static int ps5169_get_CCorientation(struct ps5169_info *info)
{
	return gpio_get_value(info->cc_gpio) + 1;
}

''' + text[end:]
assert text.count('ps5169_get_CCorientation()') == 4
text = text.replace('ps5169_get_CCorientation()', 'ps5169_get_CCorientation(info)')
assert text.count('\tps5169_get_has_dp();\t//dbg\n') == 2
text = text.replace('\tps5169_get_has_dp();\t//dbg\n', '')
start = text.index('static int ps5169_get_orientation(')
end = text.index('static int ps5169_notify_connect(', start)
text = text[:start] + text[end:]
replace('static int ps5169_release_usb_lanes(struct usb_redriver *ps5169_redriver, int num)',
        'static int ps5169_release_usb_lanes(struct usb_redriver *ps5169_redriver, int ort, int num)')
for function in ('ps5169_notify_connect', 'ps5169_release_usb_lanes'):
    start = text.index('static int ' + function + '(')
    end = text.index('\n}', start)
    part = text[start:end]
    anchor = '\tif (!ps5169_present_check())\n\t\treturn 0;'
    assert part.count(anchor) == 1
    new = anchor + '\n\tif (ort != ORIENTATION_CC1 && ort != ORIENTATION_CC2)\n\t\treturn -EINVAL;\n\tinfo->flip = ort + 1;'
    text = text[:start] + part.replace(anchor, new, 1) + text[end:]
old = '''		if(ps5169_get_CCorientation(info)) {
			ps5169_info("%s: dp_only_mode and cc, 4lane DP flow, keep ps5169.\\n", __func__);
		} else {
			ps5169_info("%s: dp_only_mode but no cc, disable ps5169.\\n", __func__);
			ps5169_remove_dp(info);
			info->op_mode = OP_MODE_NONE;
			ps5169_enable_work(info, 0);
		}'''
replace(old, '\t\t/* New redriver core calls disconnect for cable removal. */\n'
             '\t\tps5169_remove_dp(info);\n\t\tinfo->op_mode = OP_MODE_NONE;\n'
             '\t\tps5169_enable_work(info, 0);')
text = text.replace('\tinfo->ps5169_redriver.has_orientation = true;\n', '')
replace('\tinfo->ps5169_redriver.get_orientation = ps5169_get_orientation ;\n', '')
replace('\tinfo->ps5169_redriver.usb_mode = false ;\n', '')
replace('''	if(info->ps5169_redriver.usb_mode != HOST) {
		ps5169_err("%s: Device.\\n", __func__);
		ret |= ps5169_update_reg(info, 0x04, 0x44);		//disable U1 status Rx_Det
	} else {
		ps5169_err("%s: Host.\\n", __func__);
	}''', '''	/* Stock probe initializes usb_mode=false before this initial tuning. */
	ret |= ps5169_update_reg(info, 0x04, 0x44);	/* disable U1 status Rx_Det */''')
replace('void ps5169_get_chipcfg_and_modeselection(', 'static void ps5169_get_chipcfg_and_modeselection(')
replace('devm_gpio_request(dev, info->cc_gpio, "redriver")',
        'devm_gpio_request_one(dev, info->cc_gpio, GPIOF_IN, "redriver")')
replace('static int ps5169_probe(struct i2c_client *client,\n\t\tconst struct i2c_device_id *id)',
        'static int ps5169_probe(struct i2c_client *client)')
replace('static int ps5169_remove(struct i2c_client *client)',
        'static void ps5169_remove(struct i2c_client *client)')
start = text.index('static void ps5169_remove(')
end = text.index('\n}', start)
part = text[start:end].replace('return -EINVAL;', 'return;').replace('return 0;', 'return;')
text = text[:start] + part + text[end:]
text = text.replace('struct class *c', 'const struct class *c')
text = text.replace('struct class_attribute *attr', 'const struct class_attribute *attr')
text = text.replace('#include <linux/soc/qcom/battery_charger.h>\n', '')
text = text.replace('#include <linux/usb/ucsi_glink.h>\n', '#include <linux/pinctrl/consumer.h>\n')
text = '// SPDX-License-Identifier: GPL-2.0-only\n// MiCode sheng PS5169, adapted to the 6.18 redriver API.\n' + text
(stage / 'ps5169.c').write_text(text)
shutil.copyfile(source / 'drivers/usb/redriver/ps5169.h', stage / 'ps5169.h')
(stage / 'Makefile').write_text('obj-m := ps5169.o\nccflags-y += -I' + str(K618 / 'soc/include') +
                               ' -DCONFIG_USB_REDRIVER_MODULE=1\n')
log = ROOT / 'logs/ps5169-build.log'
with log.open('w') as stream:
    subprocess.run(['make','-C',str(ACK),'O='+str(OUT),'M='+str(stage),'ARCH=arm64',
                    'LLVM=1','LLVM_IAS=1','KBUILD_EXTRA_SYMBOLS='+str(K618 / 'soc/Module.symvers'),
                    '-j'+str(os.cpu_count()),'modules'], env=environment(os.cpu_count()),
                   stdout=stream,stderr=subprocess.STDOUT,check=True)
(PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/ps5169-compat.patch').write_text(
    ''.join(difflib.unified_diff(original.splitlines(True),text.splitlines(True),
        fromfile='a/drivers/usb/redriver/ps5169.c',tofile='b/drivers/usb/redriver/ps5169.c',n=0)))
native = ROOT / 'diagnostic/usb-r18'
rd = native / 'layer'
shutil.copytree(ROOT / 'diagnostic/aux-r12/layer', rd, dirs_exist_ok=True)
modules = rd / 'lib/modules'
shutil.copyfile(stage / 'ps5169.ko', modules / 'ps5169.ko')
subprocess.run([str(CLANG / 'llvm-strip'),'--strip-debug',str(modules / 'ps5169.ko')],check=True)
batch = modules / 'k618_batch.load'
text = batch.read_text()
assert 'ps5169.ko' not in text
assert text.count('i2c-msm-geni.ko\n') == 1
batch.write_text(text.replace('i2c-msm-geni.ko\n','i2c-msm-geni.ko\nps5169.ko\n'))
with (modules / 'modules.dep').open('a') as stream:
    stream.write('/lib/modules/ps5169.ko: /lib/modules/redriver.ko\n')
with (modules / 'modules.alias').open('a') as stream:
    stream.write('alias of:N*T*Cmi,ps5169 ps5169\nalias of:N*T*Cmi,ps5169C* ps5169\nalias i2c:ps5169 ps5169\n')
checked = check_candidate({p.name:ElfModule(p) for p in modules.glob('*.ko')},
                          {'source_keep_modules':['zram.ko','zsmalloc.ko']},OUT,
                          [modules/'zram.ko', modules/'zsmalloc.ko'],'6.18')
assert checked['abi_passed'], checked['issue_counts']
overlay = native / 'overlay.cpio'
names = sorted(p.relative_to(rd).as_posix() for p in rd.rglob('*'))
with overlay.open('wb') as stream:
    subprocess.run(['cpio','--null','-o','-H','newc','-R','0:0','--quiet'],
                   input=('\0'.join(names)+'\0').encode(),cwd=rd,stdout=stream,check=True)
packed = {name:(mode,data) for name,mode,data in entries(overlay.read_bytes())}
baseline = {name:(mode,data) for name,mode,data in entries((ROOT/'diagnostic/aux-r12/overlay.cpio').read_bytes())}
assert set(packed)-set(baseline) == {'lib/modules/ps5169.ko'}
assert not set(baseline)-set(packed)
assert all(packed[name][0] == baseline[name][0] for name in baseline)
changed = sorted(name for name in baseline if packed[name][1] != baseline[name][1])
assert changed == ['lib/modules/k618_batch.load','lib/modules/modules.alias','lib/modules/modules.dep'], changed
metadata = audit(overlay)
assert metadata['helper_executable'] and metadata['module_count'] == 338
report = dict(source_repository='https://github.com/MiCode/Xiaomi_Kernel_OpenSource', revision=commit,
    source_files={name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in
                  ('drivers/usb/redriver/ps5169.c','drivers/usb/redriver/ps5169.h')},
    adapted_source_sha256=hashlib.sha256((stage/'ps5169.c').read_bytes()).hexdigest(),
    module_sha256=hashlib.sha256((modules/'ps5169.ko').read_bytes()).hexdigest(),
    overlay_sha256=hashlib.sha256(overlay.read_bytes()).hexdigest(),
    checks=checked, archive=metadata, changed_existing_payloads=changed,
    evidence='Live sheng DT ssusb_redriver phandle 0x5d7 -> mi,ps5169 at a80000.i2c/ps5169@28; old 337-module overlay has no matching driver. Core returns EPROBE_DEFER until this provider registers.',
    adaptations=['6.18 I2C and const class APIs', 'Controller-provided CC1/CC2 orientation maps to PS5169 flip 1/2; wired GPIO fallback',
                 'Three-argument DP release callback; no obsolete battery charger property ABI',
                 'New redriver disconnect semantics follow selected NB7VPQ904M implementation'],
    license='GPL-2.0-only (source MODULE_LICENSE GPL v2)',
    hardware_result='pending', usb_or_displayport_functionality_claimed=False)
(PROJECT / 'reports/kernel618-ps5169-source.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(module_count=338,overlay=str(overlay),abi_passed=True),indent=2),flush=True)
