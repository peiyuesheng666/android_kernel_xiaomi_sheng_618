#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Migrate pinned LOS Kalama platform drivers into isolated ACK external modules."""
import argparse
from kernel618_portlib import Port, ROOT, PROJECT, replace, void_remove


def clocks():
    port = Port('clock-los')
    source = ROOT / 'src/lineage-kernel/drivers/clk/qcom'
    helpers = ['common', 'vdd-class', 'clk-regmap', 'clk-alpha-pll', 'clk-opp', 'clk-pll',
               'clk-rcg', 'clk-rcg2', 'clk-branch', 'clk-regmap-divider', 'clk-regmap-mux',
               'clk-regmap-mux-div', 'clk-regmap-phy-mux', 'clk-hfpll', 'reset', 'clk-pm', 'clk-debug', 'gdsc']
    controllers = [f'{name}-kalama' for name in ['gcc', 'camcc', 'dispcc', 'gpucc', 'tcsrcc', 'videocc', 'debugcc']]
    for name in helpers + controllers + ['clk-dummy']:
        def transform(text):
            if name == 'clk-opp':
                text = replace(text, '#include <linux/of_platform.h>', '#include <linux/of_platform.h>\n#include <linux/platform_device.h>')
            elif name == 'clk-alpha-pll':
                text = replace(text, '"%s failed to %s!\\n", action', '"failed to %s!\\n", action')
            elif name == 'common':
                text = replace(text, ', prop, p, i)', ', i)', 3)
                text = replace(text, '\tstruct property *prop;\n\tconst __be32 *p;\n', '', 2)
            elif name == 'clk-dummy':
                text = replace(text, 'static int dummy_clk_remove(', 'static void dummy_clk_remove(')
                text = replace(text, '\tof_clk_del_provider(pdev->dev.of_node);\n\n\treturn 0;',
                               '\tof_clk_del_provider(pdev->dev.of_node);')
            elif name == 'debugcc-kalama':
                text = replace(text, '"Unable to register %s, err:(%d)\\n",\n\t\t\t\tclk_hw_get_name',
                               '"Unable to register %s, err:(%ld)\\n",\n\t\t\t\tclk_hw_get_name')
            return text
        port.copy('lineage-kernel', f'drivers/clk/qcom/{name}.c', f'{name}.c', transform)
    for header in sorted(source.glob('*.h')):
        port.copy('lineage-kernel', header.relative_to(ROOT / 'src/lineage-kernel').as_posix(), header.name,
                  lambda text: text.replace('#include "../clk.h"', '#include <linux/clk-provider.h>')
                                   .replace('__assign_str(name, name)', '__assign_str(name)'))
    for pattern in ('include/dt-bindings/clock/*kalama*', 'include/dt-bindings/regulator/*', 'include/linux/clk/qcom.h'):
        for path in sorted((ROOT / 'src/lineage-kernel').glob(pattern)):
            port.copy('lineage-kernel', path.relative_to(ROOT / 'src/lineage-kernel').as_posix())
    port.write('Kbuild', '# SPDX-License-Identifier: GPL-2.0-only\nccflags-y += -I$(src)/include -I$(src)\n'
               'obj-m += clk-qcom.o clk-dummy.o ' + ' '.join(n + '.o' for n in controllers) + '\n'
               'clk-qcom-y := ' + ' '.join(n + '.o' for n in helpers) + '\n')
    port.finish(['clk-qcom.ko', 'clk-dummy.ko'] + [n + '.ko' for n in controllers],
                ['Replaces the earlier ACK-helper/TCSR experiment; never load both clk-qcom variants.',
                 'No physical validation; downstream DEEPSLEEP is not enabled.'])
    return port.build()


def pinctrl():
    port = Port('pinctrl')
    for name in ['pinctrl-msm.c', 'pinctrl-msm.h', 'pinctrl-kalama.c']:
        def transform(text):
            text = text.replace('<linux/qcom_scm.h>', '<linux/firmware/qcom/qcom_scm.h>')
            if name == 'pinctrl-msm.c':
                # LEVEL retains the old OUTPUT parameter's value-driving semantics.
                import re
                text, count = re.subn(r'\bPIN_CONFIG_OUTPUT\b', 'PIN_CONFIG_LEVEL', text)
                assert count == 3
                text = replace(text, ', prop, p, i)', ', i)')
                text = replace(text, '\tstruct property *prop;\n\tconst __be32 *p;\n', '')
                text = replace(text, 'static void msm_gpio_set(', 'static int msm_gpio_set(')
                text = replace(text, '\traw_spin_unlock_irqrestore(&pctrl->lock, flags);\n}\n\n#ifdef CONFIG_DEBUG_FS',
                               '\traw_spin_unlock_irqrestore(&pctrl->lock, flags);\n\treturn 0;\n}\n\n#ifdef CONFIG_DEBUG_FS')
                text = replace(text, 'chip->of_node = pctrl->dev->of_node;', 'chip->fwnode = dev_fwnode(pctrl->dev);')
                text = replace(text, '!test_bit(i, pctrl->chip.valid_mask)', '!gpiochip_line_is_valid(&pctrl->chip, i)', 2)
                text = replace(text, '"The tile addr generated is 0x%lx\\n", (u64)tile_addr',
                               '"The tile addr generated is %p\\n", tile_addr', 2)
                text = replace(text, 'int msm_pinctrl_remove(', 'void msm_pinctrl_remove(')
                text = replace(text, '\tunregister_restart_handler(&pctrl->restart_nb);\n\n\treturn 0;',
                               '\tunregister_restart_handler(&pctrl->restart_nb);')
            elif name == 'pinctrl-msm.h':
                text = replace(text, 'int msm_pinctrl_remove(', 'void msm_pinctrl_remove(')
            return text
        port.copy('lineage-kernel', f'drivers/pinctrl/qcom/{name}', name,
                  transform)
    for name in ['include/linux/pinctrl/qcom-pinctrl.h', 'include/linux/soc/qcom/irq.h']:
        port.copy('lineage-kernel', name)
    port.write('Kbuild', '# SPDX-License-Identifier: GPL-2.0-only\n'
               'ccflags-y += -I$(src)/include -I$(srctree)/drivers/pinctrl/qcom\n'
               'obj-m += pinctrl-msm.o pinctrl-kalama.o\n')
    port.finish(['pinctrl-msm.ko', 'pinctrl-kalama.ko'])
    return port.build(['firmware'])


def firmware():
    port = Port('firmware')
    names = ['qcom_scm.c', 'qcom_scm-smc.c', 'qcom_scm-legacy.c', 'qcom_scm.h',
             'qtee_shmbridge.c', 'qtee_shmbridge_internal.h']
    for name in names:
        def transform(text):
            if name == 'qcom_scm.c':
                for func in ['__qcom_scm_get_feat_version', '__qcom_scm_lmh_debug_config_write', 'qcom_scm_custom_reboot']:
                    text = replace(text, 'int ' + func + '(', 'static int ' + func + '(')
                text = replace(text, 'wq_ctx %d: %d', 'wq_ctx %d: %ld')
                text = replace(text, 'offset of pid is %zu, offset of comm is %zu', 'offset of pid is %u, offset of comm is %u')
            elif name == 'qtee_shmbridge.c':
                text = replace(text, '#include <linux/msm_ion.h>\n', '')
                text = replace(text, '"%s: found 0%x already exist with shmbridge\\n",\n\t\t\t__func__, paddr',
                               '"%s: found %pa already exist with shmbridge\\n",\n\t\t\t__func__, &paddr')
                text = replace(text, 'bridge size %d', 'bridge size %zu')
                text = replace(text, 'bridge with size %d', 'bridge with size %zu', 2)
                text = replace(text, 'static int qtee_shmbridge_remove(', 'static void qtee_shmbridge_remove(')
                text = replace(text, '\tfree_pages((long)default_bridge.vaddr, get_order(default_bridge.size));\n\treturn 0;',
                               '\tfree_pages((long)default_bridge.vaddr, get_order(default_bridge.size));')
            elif name == 'qcom_scm-smc.c':
                text = replace(text, 'wq_ctx %d: %d', 'wq_ctx %d: %ld')
            return text
        port.copy('lineage-kernel', 'drivers/firmware/' + name, name, transform)
    for name in ['include/linux/qcom_scm.h', 'include/linux/qtee_shmbridge.h',
                 'include/linux/qcom_scm_hab.h', 'include/uapi/linux/msm_ion.h',
                 'include/soc/qcom/secure_buffer.h',
                 'include/soc/qcom/qseecom_scm.h', 'include/soc/qcom/qseecomi.h',
                 'include/uapi/linux/qseecom.h', 'include/uapi/linux/ion.h']:
        if (ROOT / 'src/lineage-kernel' / name).exists():
            port.copy('lineage-kernel', name)
    port.write('Kbuild', '# SPDX-License-Identifier: GPL-2.0-only\n'
               'ccflags-y += -I$(src)/include -I$(src)/include/uapi -DCONFIG_QCOM_SCM_MODULE=1 -DCONFIG_QTEE_SHM_BRIDGE=1\n'
               'obj-m += qcom-scm.o\n'
               'qcom-scm-y := qcom_scm.o qcom_scm-smc.o qcom_scm-legacy.o qtee_shmbridge.o\n')
    port.finish(['qcom-scm.ko'])
    return port.build()


def rpmh():
    port = Port('rpmh')
    paths = ['drivers/soc/qcom/' + name for name in
             ['rpmh-rsc.c', 'rpmh.c', 'rpmh-internal.h', 'cmd-db.c', 'trace-rpmh.h']]
    paths += ['kernel/trace/' + name for name in ['ipc_logging.c', 'ipc_logging_private.h', 'ipc_logging_debug.c']]
    paths += ['drivers/clk/qcom/clk-rpmh.c', 'drivers/regulator/qcom-rpmh-regulator.c']
    paths += ['include/soc/qcom/' + name for name in ['rpmh.h', 'tcs.h', 'cmd-db.h']]
    paths += ['include/linux/ipc_logging.h', 'include/dt-bindings/soc/qcom,rpmh-rsc.h',
              'include/soc/qcom/minidump.h',
              'include/dt-bindings/clock/qcom,rpmh.h', 'include/dt-bindings/regulator/qcom,rpmh-regulator.h']
    for path in paths:
        if not (ROOT / 'src/lineage-kernel' / path).exists():
            raise FileNotFoundError(path)
        target = path if path.startswith('include/') else path.rsplit('/', 1)[-1]
        port.copy('lineage-kernel', path, target,
                  lambda text: text.replace('__assign_str(name, d->name)', '__assign_str(name)')
                                   .replace('int rpmh_rsc_is_tcs_completed(', 'static int rpmh_rsc_is_tcs_completed('))
    port.write('Kbuild', '# SPDX-License-Identifier: GPL-2.0-only\n'
               'LINUXINCLUDE := -I$(src)/include $(LINUXINCLUDE)\n'
               'ccflags-y += -I$(src)/include -I$(src) -DCONFIG_QCOM_RPMH_MODULE=1 -DCONFIG_QCOM_COMMAND_DB_MODULE=1 -DCONFIG_IPC_LOGGING=1 -DCONFIG_IPC_LOG_MINIDUMP_BUFFERS=0\n'
               'obj-m += qcom_rpmh.o cmd-db.o ipc-logging.o clk-rpmh.o qcom-rpmh-regulator.o\n'
               'qcom_rpmh-y := rpmh-rsc.o rpmh.o\n'
               'ipc-logging-y := ipc_logging.o ipc_logging_debug.o\n')
    port.finish(['qcom_rpmh.ko', 'cmd-db.ko', 'ipc-logging.ko', 'clk-rpmh.ko', 'qcom-rpmh-regulator.ko'])
    return port.build()


def interconnect():
    port = Port('interconnect')
    names = ['kalama.c', 'icc-rpmh.c', 'icc-rpmh.h', 'bcm-voter.c', 'bcm-voter.h',
             'qnoc-qos.c', 'qnoc-qos.h', 'trace.h']
    for name in names:
        def transform(text):
            # Avoid duplicating ACK's already built-in translator export.
            text = text.replace('qcom_icc_xlate_extended', 'sheng_icc_xlate_extended')
            if name == 'trace.h':
                text = replace(text, '__assign_str(state_name, rpmh_state)', '__assign_str(state_name)')
            if name == 'icc-rpmh.h':
                text = replace(text, 'int qcom_icc_rpmh_remove(', 'void qcom_icc_rpmh_remove(')
                text = replace(text, 'sheng_icc_xlate_extended(struct of_phandle_args *spec',
                               'sheng_icc_xlate_extended(const struct of_phandle_args *spec')
            if name == 'icc-rpmh.c':
                text = replace(text, 'int qcom_icc_rpmh_remove(', 'void qcom_icc_rpmh_remove(')
                text = replace(text, 'sheng_icc_xlate_extended(struct of_phandle_args *spec',
                               'sheng_icc_xlate_extended(const struct of_phandle_args *spec')
                text = replace(text, 'INIT_LIST_HEAD(&provider->nodes);', 'icc_provider_init(provider);')
                text = replace(text, '\tret = icc_provider_add(provider);\n\tif (ret)\n\t\treturn ret;\n\n', '')
                text = replace(text, '#ifdef CONFIG_INTERCONNECT_QCOM_DEBUG\n\tqcom_icc_debug_register(provider);',
                               '\tret = icc_provider_register(provider);\n\tif (ret)\n\t\tgoto err;\n\n'
                               '#ifdef CONFIG_INTERCONNECT_QCOM_DEBUG\n\tqcom_icc_debug_register(provider);')
                # The bulk clocks were acquired by devm_clk_bulk_get_all().
                text = replace(text, '\tclk_bulk_put_all(qp->num_clks, qp->clks);\n', '', 2)
                text = replace(text, '\ticc_provider_del(provider);\n', '')
                text = replace(text, '\ticc_nodes_remove(&qp->provider);\n\treturn icc_provider_del(&qp->provider);',
                               '\tmutex_lock(&probe_list_lock);\n\tlist_del(&qp->probe_list);\n'
                               '\tmutex_unlock(&probe_list_lock);\n\ticc_provider_deregister(&qp->provider);\n'
                               '\ticc_nodes_remove(&qp->provider);')
            if name == 'bcm-voter.c':
                text = void_remove(text, 'qcom_icc_bcm_voter_remove')
            return text
        port.copy('lineage-kernel', f'drivers/interconnect/qcom/{name}', name, transform)
    port.copy('lineage-kernel', 'include/dt-bindings/interconnect/qcom,kalama.h')
    port.copy('lineage-kernel', 'include/dt-bindings/interconnect/qcom,icc.h')
    port.write('Kbuild', '# SPDX-License-Identifier: GPL-2.0-only\n'
               'LINUXINCLUDE := -I$(src)/include -I$(src)/../rpmh/include -I$(src)/../soc/include $(LINUXINCLUDE)\n'
               'ccflags-y += -I$(src) -DCONFIG_QCOM_RPMH_MODULE=1 -DCONFIG_QCOM_COMMAND_DB_MODULE=1 -DCONFIG_QCOM_SOCINFO_MODULE=1\n'
               'obj-m += qnoc-kalama.o icc-rpmh.o icc-bcm-voter.o qnoc-qos.o\n'
               'qnoc-kalama-y := kalama.o\nicc-bcm-voter-y := bcm-voter.o\n')
    port.finish(['qnoc-kalama.ko', 'icc-rpmh.ko', 'icc-bcm-voter.ko', 'qnoc-qos.ko'])
    return port.build(['rpmh', 'soc'])


def soc():
    port = Port('soc')
    paths = ['drivers/soc/qcom/' + name for name in ['smem.c', 'socinfo.c', 'smp2p.c', 'qcom_aoss.c']]
    paths += ['drivers/hwspinlock/qcom_hwspinlock.c', 'drivers/mailbox/qcom-ipcc.c']
    paths += ['include/linux/soc/qcom/' + name for name in ['smem.h', 'qcom_aoss.h']]
    paths += ['include/soc/qcom/socinfo.h', 'include/dt-bindings/power/qcom-aoss-qmp.h',
              'include/dt-bindings/mailbox/qcom-ipcc.h']
    for path in paths:
        target = path if path.startswith('include/') else path.rsplit('/', 1)[-1]
        def transform(text):
            text = text.replace('<asm/unaligned.h>', '<linux/unaligned.h>')
            callbacks = {'smem.c': 'qcom_smem_remove', 'socinfo.c': 'qcom_socinfo_remove',
                         'smp2p.c': 'qcom_smp2p_remove', 'qcom_aoss.c': 'qmp_remove', 'qcom-ipcc.c': 'qcom_ipcc_remove'}
            if target in callbacks:
                text = void_remove(text, callbacks[target])
            if target == 'socinfo.c':
                import re
                # The versioned sysfs attributes intentionally accumulate older fields.
                text, count = re.subn(r'(\.attr;\n)(\tcase SOCINFO_VERSION)', r'\1\t\tfallthrough;\n\2', text)
                assert count == 12
                text = replace(text, 'void socinfo_enumerate_partinfo_details(', 'static void socinfo_enumerate_partinfo_details(')
            elif target == 'smp2p.c':
                text = replace(text, 'strlcpy(', 'strscpy(')
            elif target == 'qcom_aoss.c':
                text = replace(text, ', len, (char *)data)', ', (int)len, (char *)data)', 3)
                text = replace(text, 'wait error %d', 'wait error %ld')
            return text
        port.copy('lineage-kernel', path, target, transform)
    port.write('Kbuild', '# SPDX-License-Identifier: GPL-2.0-only\n'
               'LINUXINCLUDE := -I$(src)/include -I$(src)/../rpmh/include $(LINUXINCLUDE)\n'
               'ccflags-y += -I$(srctree)/drivers/hwspinlock -DCONFIG_QCOM_SMEM_MODULE=1 -DCONFIG_QCOM_SOCINFO_MODULE=1 -DCONFIG_IPC_LOGGING=1 -DCONFIG_QCOM_AOSS_QMP_MODULE=1\n'
               'obj-m += smem.o socinfo.o smp2p.o qcom_aoss.o qcom_hwspinlock.o qcom-ipcc.o\n')
    port.finish(['smem.ko', 'socinfo.ko', 'smp2p.ko', 'qcom_aoss.ko', 'qcom_hwspinlock.ko', 'qcom-ipcc.ko'])
    return port.build(['rpmh'])


def pmic():
    port = Port('pmic')
    paths = ['drivers/spmi/spmi-pmic-arb.c', 'drivers/mfd/qcom-spmi-pmic.c',
             'drivers/pinctrl/qcom/pinctrl-spmi-gpio.c', 'drivers/pinctrl/qcom/pinctrl-spmi-mpp.c',
             'drivers/nvmem/qcom-spmi-sdam.c', 'drivers/irqchip/qcom-pdc.c',
             'drivers/clk/qcom/gdsc-regulator.c', 'drivers/regulator/proxy-consumer.c']
    headers = ['include/linux/soc/qcom/spmi-pmic-arb.h', 'include/linux/qti-regmap-debugfs.h',
               'include/dt-bindings/pinctrl/qcom,pmic-gpio.h',
               'include/linux/regulator/debug-regulator.h', 'include/linux/regulator/proxy-consumer.h',
               'include/linux/mailbox/qmp.h', 'drivers/clk/qcom/gdsc-debug.h', 'drivers/clk/qcom/trace-gdsc.h']
    for path in paths + headers:
        target = path if path.startswith('include/') else path.rsplit('/', 1)[-1]
        def transform(text):
            import re
            callbacks = {'spmi-pmic-arb.c': 'spmi_pmic_arb_remove', 'pinctrl-spmi-gpio.c': 'pmic_gpio_remove',
                         'pinctrl-spmi-mpp.c': 'pmic_mpp_remove'}
            if target in callbacks:
                text = void_remove(text, callbacks[target])
            if target == 'qcom-spmi-sdam.c':
                text = replace(text, '#include <linux/of_platform.h>', '#include <linux/of_platform.h>\n#include <linux/platform_device.h>')
            if target == 'qcom-spmi-pmic.c':
                text = replace(text, '#include <linux/of_platform.h>', '#include <linux/of_platform.h>\n#include <linux/of.h>')
            if target in ['pinctrl-spmi-gpio.c', 'pinctrl-spmi-mpp.c']:
                text = re.sub(r'\bPIN_CONFIG_OUTPUT\b', 'PIN_CONFIG_LEVEL', text)
                prefix = 'pmic_gpio' if target == 'pinctrl-spmi-gpio.c' else 'pmic_mpp'
                text = replace(text, 'static void ' + prefix + '_set(', 'static int ' + prefix + '_set(')
                text = replace(text, '\t' + prefix + '_config_set(state->ctrl, pin, &config, 1);',
                               '\treturn ' + prefix + '_config_set(state->ctrl, pin, &config, 1);')
                text = replace(text, '#include <linux/module.h>', '#include <linux/module.h>\n#include <linux/seq_file.h>')
            if target == 'pinctrl-spmi-gpio.c':
                text = replace(text, 'static void *pmic_gpio_populate_parent_fwspec(struct gpio_chip *chip,',
                               'static int pmic_gpio_populate_parent_fwspec(struct gpio_chip *chip,\n'
                               '\t\t\t\t\t     union gpio_irq_fwspec *gfwspec,')
                text = replace(text, '\tstruct irq_fwspec *fwspec;\n\n\tfwspec = kzalloc(sizeof(*fwspec), GFP_KERNEL);\n'
                               '\tif (!fwspec)\n\t\treturn NULL;', '\tstruct irq_fwspec *fwspec = &gfwspec->fwspec;')
                text = replace(text, '\treturn fwspec;', '\treturn 0;')
            if target == 'qcom-pdc.c':
                text = replace(text, 'PIN=%d', 'PIN=%lu', 4)
                text = replace(text, 'PIN=%lu GIC-SPI=%d', 'PIN=%lu GIC-SPI=%lu', 2)
                text = replace(text, 'qcom_pdc_init(struct device_node *node, struct device_node *parent)',
                               'qcom_pdc_init(struct platform_device *pdev, struct device_node *parent)')
                text = replace(text, '#include <linux/module.h>', '#include <linux/module.h>\n#include <linux/platform_device.h>')
                text = replace(text, 'static int qcom_pdc_init(struct platform_device *pdev, struct device_node *parent)\n{',
                               'static int qcom_pdc_init(struct platform_device *pdev, struct device_node *parent)\n{\n'
                               '\tstruct device_node *node = pdev->dev.of_node;')
            if target == 'gdsc-regulator.c':
                text = replace(text, '#include "../../regulator/internal.h"', '#include "regulator-internal.h"')
                text = replace(text, 'ww_mutex_trylock(&parent_rdev->mutex)', 'ww_mutex_trylock(&parent_rdev->mutex, NULL)', 2)
            if target == 'proxy-consumer.c':
                text = text.replace('#include "internal.h"', '#include "regulator-internal.h"')
            if target == 'trace-gdsc.h':
                text = re.sub(r'__assign_str\((\w+), [^;]+\);', r'__assign_str(\1);', text)
            return text
        port.copy('lineage-kernel', path, target, transform)
    port.copy('ack', 'drivers/regulator/internal.h', 'regulator-internal.h')
    port.write('Kbuild', '# SPDX-License-Identifier: GPL-2.0-only\n'
               'LINUXINCLUDE := -I$(src)/include -I$(src)/../firmware/include -I$(src)/../rpmh/include -I$(src)/../pinctrl/include $(LINUXINCLUDE)\n'
               'ccflags-y += -I$(src) -I$(srctree)/drivers/pinctrl/qcom -DCONFIG_IPC_LOGGING=1 -DCONFIG_SPMI_MSM_PMIC_ARB_MODULE=1 -DCONFIG_QCOM_GDSC_REGULATOR_MODULE=1 -DCONFIG_REGULATOR_PROXY_CONSUMER_MODULE=1\n'
               'obj-m += ' + ' '.join(p.rsplit('/', 1)[-1][:-2] + '.o' for p in paths) + '\n')
    port.finish([p.rsplit('/', 1)[-1][:-2] + '.ko' for p in paths],
                ['QTI regmap diagnostic debugfs extension is not enabled.'])
    return port.build(['firmware', 'rpmh'])


def ufs_phy():
    port = Port('ufs-phy')
    for name in ['phy-qcom-ufs.c', 'phy-qcom-ufs-i.h', 'phy-qcom-ufs-qmp-v4-kalama.c', 'phy-qcom-ufs-qmp-v4-kalama.h']:
        port.copy('lineage-kernel', 'drivers/phy/qualcomm/' + name, name,
                  lambda text: text.replace('"%s: unsupported submode.\\n");',
                                            '"%s: unsupported submode.\\n", __func__);'))
    port.copy('lineage-kernel', 'include/linux/phy/phy-qcom-ufs.h', transform=lambda text:
              replace(text, '#include "phy.h"', '#include <linux/phy/phy.h>'))
    port.write('Kbuild', '# SPDX-License-Identifier: GPL-2.0-only\n'
               'LINUXINCLUDE := -I$(src)/include -I$(src)/../rpmh/include $(LINUXINCLUDE)\n'
               'obj-m += phy-qcom-ufs.o phy-qcom-ufs-qmp-v4-kalama.o\n')
    port.finish(['phy-qcom-ufs.ko', 'phy-qcom-ufs-qmp-v4-kalama.ko'])
    return port.build()


def ipc():
    port = Port('ipc')
    paths = ['drivers/rpmsg/' + n for n in ['qcom_glink_native.c', 'qcom_glink_native.h',
             'qcom_glink_smem.c', 'qcom_glink_ssr.c', 'qcom_glink_memshare.c']]
    paths += ['drivers/remoteproc/' + n for n in ['qcom_common.c', 'qcom_common.h', 'qcom_tracepoints.c']]
    paths += ['drivers/soc/qcom/' + n for n in ['qmi_encdec.c', 'qmi_interface.c', 'pdr_interface.c',
              'pdr_internal.h', 'pmic_glink.c', 'glink_probe.c', 'glink_pkt.c']]
    paths += ['include/linux/soc/qcom/' + n for n in ['qmi.h', 'pdr.h', 'pmic_glink.h']]
    paths += ['include/linux/remoteproc/qcom_rproc.h', 'include/linux/rpmsg/qcom_glink.h',
              'include/trace/events/rproc_qcom.h', 'include/soc/qcom/rpm-smd.h', 'include/soc/qcom/subsystem_notif.h']
    for path in paths:
        target = path if path.startswith('include/') else path.rsplit('/', 1)[-1]
        def transform(text):
            import re
            text = text.replace('#include "../../remoteproc/qcom_common.h"', '#include "qcom_common.h"')
            text = text.replace('<asm/unaligned.h>', '<linux/unaligned.h>')
            if path.endswith('.h'):
                text = re.sub(r'__assign_str\((\w+), [^;]+\);', r'__assign_str(\1);', text)
            if target in ['pdr_interface.c', 'qcom_common.c']:
                text = text.replace('from_timer(', 'timer_container_of(').replace('del_timer_sync(', 'timer_delete_sync(')
            if target == 'qcom_glink_ssr.c':
                text = replace(text, 'strlcpy(', 'strscpy(')
            if target == 'qcom_glink_memshare.c':
                text = replace(text, '#include <linux/device.h>', '#include <linux/device.h>\n'
                               '#include <linux/rpmsg/qcom_glink.h>\n#include "qcom_glink_native.h"')
            if target == 'pmic_glink.c':
                text = replace(text, '\tdown_read(&client->pgdev->rpdev_sem);',
                               '\tif (!data || len < sizeof(struct pmic_glink_hdr) || len > INT_MAX)\n'
                               '\t\treturn -EINVAL;\n\n\tdown_read(&client->pgdev->rpdev_sem);')
                text = replace(text, '#include <linux/of_platform.h>', '#include <linux/of_platform.h>\n#include <linux/of.h>')
                text = replace(text, 'len, data, client->name, rc)', '(int)min_t(size_t, len, 64), data, client->name, rc)')
                text = replace(text, ', len, data)', ', (int)min_t(size_t, len, 64), data)', 2)
                text = replace(text, ', pbuf->len, pbuf->buf)', ', (int)min_t(size_t, pbuf->len, 64), pbuf->buf)')
                text = replace(text, ', hdr->owner, pbuf->len,', ', hdr->owner, (int)min_t(size_t, pbuf->len, 64),')
                text = replace(text, 'debugfs directory rc=%d', 'debugfs directory rc=%ld')
                text = void_remove(text, 'pmic_glink_remove')
            if target == 'glink_probe.c':
                text = void_remove(text, 'glink_remove')
            if target == 'glink_pkt.c':
                text = replace(text, '#include <linux/rpmsg.h>', '#include <linux/rpmsg.h>\n#include "sheng-rpmsg.h"')
                text = replace(text, '(rpdev->ept->rx_done) ? true : false', 'sheng_rpmsg_supports_rx_done(rpdev->ept)')
                text = replace(text, '(rpdev->ept->rx_done) ?', 'sheng_rpmsg_supports_rx_done(rpdev->ept) ?')
                text = replace(text, 'remaining[%d], count[%d]', 'remaining[%zu], count[%zu]')
                text = replace(text, 'ret[%d], remaining[%d]', 'ret[%d], remaining[%zu]')
                text = replace(text, 'vma->vm_flags &= ~(VM_MAYWRITE | VM_MAYEXEC);',
                               'vm_flags_clear(vma, VM_MAYWRITE | VM_MAYEXEC);')
                text = replace(text, 'vma->vm_flags |= VM_MIXEDMAP;', 'vm_flags_set(vma, VM_MIXEDMAP);')
                text = text.replace('ida_simple_remove(', 'ida_free(')
                text = replace(text, 'ida_simple_get(&glink_pkt_minor_ida, 0, num_glink_pkt_devs,',
                               'ida_alloc_range(&glink_pkt_minor_ida, 0, num_glink_pkt_devs - 1,')
                text = replace(text, '\trpdrv->signals = glink_pkt_rpdev_sigs;\n', '')
                text = replace(text, 'static int glink_pkt_rpdev_probe(struct rpmsg_device *rpdev)',
                               'static int glink_pkt_rpdev_sigs(struct rpmsg_device *rpdev, void *priv, u32 old, u32 new);\n\n'
                               'static int glink_pkt_rpdev_probe(struct rpmsg_device *rpdev)')
                text = replace(text, '\tdev_set_drvdata(&rpdev->dev, gpdev);\n\tcomplete_all(&gpdev->ch_open);',
                               '\tdev_set_drvdata(&rpdev->dev, gpdev);\n'
                               '\tsheng_rpmsg_set_signals_callback(rpdev->ept, glink_pkt_rpdev_sigs);\n'
                               '\tcomplete_all(&gpdev->ch_open);')
                text = replace(text, 'class_create(THIS_MODULE, "glinkpkt")', 'class_create("glinkpkt")')
                text = replace(text, '\tmutex_lock(&gpdev->lock);\n\tglink_pkt_clear_queues(gpdev);',
                               '\tsheng_rpmsg_set_signals_callback(rpdev->ept, NULL);\n'
                               '\tmutex_lock(&gpdev->lock);\n\tglink_pkt_clear_queues(gpdev);')
                text = replace(text, '\t\tida_free(&glink_pkt_minor_ida, MINOR(dev->devt));\n\t\tkfree(gpdev);',
                               '\t\tida_free(&glink_pkt_minor_ida, minor);\n\t\tkfree(gpdev);', 2)
            if target == 'qcom_glink_native.c':
                text = replace(text, '#include <linux/rpmsg.h>', '#include <linux/rpmsg.h>\n'
                               '#include <linux/rpmsg/qcom_glink.h>\n#include "sheng-rpmsg.h"')
                text = replace(text, 'struct glink_channel {\n\tstruct rpmsg_endpoint ept;',
                               'struct glink_channel {\n\tstruct rpmsg_endpoint ept;\n'
                               '\tbool rx_done;\n\tsheng_rpmsg_rx_sig_t sig_cb;')
                text = replace(text, 'channel->ept.rx_done', 'channel->rx_done', 2)
                text = replace(text, 'ept->rx_done = true;', 'channel->rx_done = true;')
                text = replace(text, 'channel->ept.sig_cb', 'channel->sig_cb', 2)
                text = replace(text, '\tif (channel->sig_cb) {', '\tspin_lock_irqsave(&channel->recv_lock, flags);\n\tif (channel->sig_cb) {')
                # The receive-signals function already owns a channel reference.
                start = text.rindex('static int ', 0, text.index('channel->sig_cb) {'))
                end = text.index('\nstatic ', start + 1)
                chunk = text[start:end]
                chunk = replace(chunk, '\tu32 old;', '\tu32 old;\n\tunsigned long flags;')
                chunk = replace(chunk, '\tqcom_glink_channel_ref_put(channel);',
                                '\tspin_unlock_irqrestore(&channel->recv_lock, flags);\n\tqcom_glink_channel_ref_put(channel);')
                text = text[:start] + chunk + text[end:]
                for field, func in [('rx_done', 'qcom_glink_rx_done'), ('get_signals', 'qcom_glink_get_sigs'), ('set_signals', 'qcom_glink_set_sigs')]:
                    text = replace(text, f'\t.{field} = {func},\n', '')
                text = replace(text, 'zero copy req wrong intent liid:%d size:%d', 'zero copy req wrong intent liid:%d size:%zu')
                text = replace(text, 'da:0x%llx va:0x%llx', 'da:0x%llx va:%p')
                text += '\n#include "glink-rpmsg-extensions.inc"\n#include "glink-signals-callback.inc"\n'
            return text
        port.copy('lineage-kernel', path, target, transform)
    def extensions(text):
        start = text.index('int rpmsg_get_signals(')
        end = text.index('EXPORT_SYMBOL(rpmsg_rx_done);', start) + len('EXPORT_SYMBOL(rpmsg_rx_done);')
        text = text[start:end]
        for member, function in [('get_signals', 'qcom_glink_get_sigs'), ('set_signals', 'qcom_glink_set_sigs'), ('rx_done', 'qcom_glink_rx_done')]:
            text = replace(text, f'!ept->ops->{member}', 'ept->ops != &glink_endpoint_ops')
            text = replace(text, f'ept->ops->{member}(ept,', function + '(ept,') if member != 'get_signals' else replace(text, 'ept->ops->get_signals(ept)', 'qcom_glink_get_sigs(ept)')
        return replace(text, '!ept->rx_done', '!to_glink_channel(ept)->rx_done') + '\n'
    port.copy('lineage-kernel', 'drivers/rpmsg/rpmsg_core.c', 'glink-rpmsg-extensions.inc', extensions)
    compat = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/compat'
    for name in ['sheng-rpmsg.h', 'glink-signals-callback.inc']:
        port.write(name, (compat / name).read_bytes())
    port.write('Kbuild', '# SPDX-License-Identifier: GPL-2.0-only\n'
               'LINUXINCLUDE := -I$(src)/include -I$(src)/../soc/include -I$(src)/../rpmh/include $(LINUXINCLUDE)\n'
               'ccflags-y += -I$(src) -I$(srctree)/drivers/rpmsg -I$(srctree)/drivers/remoteproc '
               '-DCONFIG_IPC_LOGGING=1 -DCONFIG_QCOM_SMEM_MODULE=1 -DCONFIG_QCOM_RPROC_COMMON_MODULE=1 '
               '-DCONFIG_RPMSG_QCOM_GLINK_MODULE=1 -DCONFIG_RPMSG_QCOM_GLINK_SMEM_MODULE=1 '
               '-DCONFIG_QCOM_QMI_HELPERS_MODULE=1 -DCONFIG_QCOM_PDR_HELPERS_MODULE=1 -DCONFIG_QTI_PMIC_GLINK_MODULE=1\n'
               'ccflags-y += -DCONFIG_RPROC_SSR_NOTIF_TIMEOUT=10000 -DCONFIG_PDR_INDICATION_NOTIF_TIMEOUT=3000\n'
               'obj-m += qcom_glink.o qcom_glink_smem.o rproc_qcom_common.o qmi_helpers.o pdr_interface.o pmic_glink.o glink_probe.o glink_pkt.o\n'
               'qcom_glink-y := qcom_glink_native.o qcom_glink_ssr.o qcom_glink_memshare.o\n'
               'rproc_qcom_common-y := qcom_common.o qcom_tracepoints.o\n'
               'qmi_helpers-y := qmi_encdec.o qmi_interface.o\n')
    port.finish(['qcom_glink.ko', 'qcom_glink_smem.ko', 'rproc_qcom_common.ko', 'qmi_helpers.ko',
                 'pdr_interface.ko', 'pmic_glink.ko', 'glink_probe.ko', 'glink_pkt.ko'])
    return port.build(['rpmh', 'soc'])


def remoteproc():
    port = Port('remoteproc')
    paths = ['drivers/remoteproc/' + n for n in
             ['qcom_q6v5.c', 'qcom_q6v5.h', 'qcom_q6v5_pas.c', 'qcom_sysmon.c',
              'qcom_pil_info.c', 'qcom_pil_info.h']]
    paths += ['drivers/soc/qcom/' + n for n in
              ['mdt_loader.c', 'secure_buffer.c', 'trace_secure_buffer.h', 'qcom_ramdump.c']]
    paths += ['include/linux/soc/qcom/mdt_loader.h', 'include/soc/qcom/qcom_ramdump.h']
    for path in paths:
        target = path if path.startswith('include/') else path.rsplit('/', 1)[-1]
        def transform(text):
            import re
            text = text.replace('<asm/unaligned.h>', '<linux/unaligned.h>')
            if target.endswith('.h'):
                text = re.sub(r'__assign_str\((\w+), [^;]+\);', r'__assign_str(\1);', text)
            if target == 'qcom_q6v5_pas.c':
                text = void_remove(text, 'adsp_remove')
                text = replace(text, '"%zu\\n", qcom_sysmon_get_txn_id', '"%u\\n", qcom_sysmon_get_txn_id')
                text = replace(text, 'void adsp_segment_dump(', 'static void adsp_segment_dump(')
            if target == 'qcom_sysmon.c':
                text = text.replace('from_timer(', 'timer_container_of(').replace('del_timer_sync(', 'timer_delete_sync(')
            if target == 'mdt_loader.c':
                text = replace(text, '"b%02d", hash_index', '"b%02zu", hash_index')
            if target == 'qcom_ramdump.c':
                text = replace(text, 'Got segment size %d', 'Got segment size %zu')
                text = replace(text, 'Creating elf with size %d', 'Creating elf with size %zu')
                text = replace(text, 'class_create(THIS_MODULE, RAMDUMP_NAME)', 'class_create(RAMDUMP_NAME)')
                text = replace(text, 'ida_simple_get(&rd_minor_id, 0, RAMDUMP_NUM_DEVICES,',
                               'ida_alloc_range(&rd_minor_id, 0, RAMDUMP_NUM_DEVICES - 1,')
                text = text.replace('ida_simple_remove(', 'ida_free(')
            if target == 'trace_secure_buffer.h':
                text = replace(text, 'TRACE_INCLUDE_PATH ../../drivers/soc/qcom/', 'TRACE_INCLUDE_PATH .')
            if target == 'secure_buffer.c':
                text = replace(text, 'nth_page(sg_page(sg), npages)',
                               'pfn_to_page(page_to_pfn(sg_page(sg)) + npages)')
            return text
        port.copy('lineage-kernel', path, target, transform)
    port.write('Kbuild', '# SPDX-License-Identifier: GPL-2.0-only\n'
               'LINUXINCLUDE := -I$(src)/include -I$(src)/../firmware/include -I$(src)/../ipc/include '
               '-I$(src)/../soc/include -I$(src)/../rpmh/include $(LINUXINCLUDE)\n'
               'ccflags-y += -I$(src) -I$(src)/../ipc -I$(srctree)/drivers/remoteproc '
               '-DCONFIG_QCOM_SCM_MODULE=1 -DCONFIG_QCOM_RPROC_COMMON_MODULE=1 '
               '-DCONFIG_QCOM_Q6V5_COMMON_MODULE=1 -DCONFIG_QCOM_SYSMON_MODULE=1 '
               '-DCONFIG_QCOM_PIL_INFO_MODULE=1 -DCONFIG_QCOM_MDT_LOADER_MODULE=1 '
               '-DCONFIG_QCOM_SECURE_BUFFER_MODULE=1 -DCONFIG_QCOM_RAMDUMP_MODULE=1 '
               '-DCONFIG_QCOM_SMEM_MODULE=1 -DCONFIG_QCOM_QMI_HELPERS_MODULE=1 -DCONFIG_QCOM_AOSS_QMP_MODULE=1\n'
               'ccflags-y += -DCONFIG_RPROC_SYSMON_NOTIF_TIMEOUT=10000 -DCONFIG_RPROC_SYSMON_SHUTDOWN_NOTIF_TIMEOUT=10000\n'
               'obj-m += qcom_q6v5.o qcom_q6v5_pas.o qcom_sysmon.o qcom_pil_info.o mdt_loader.o secure_buffer.o qcom_ramdump.o\n')
    port.finish(['qcom_q6v5.ko', 'qcom_q6v5_pas.ko', 'qcom_sysmon.ko', 'qcom_pil_info.ko',
                 'mdt_loader.ko', 'secure_buffer.ko', 'qcom_ramdump.ko'])
    return port.build(['firmware', 'rpmh', 'soc', 'ipc'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    groups = {'clocks': clocks, 'firmware': firmware, 'pinctrl': pinctrl, 'rpmh': rpmh,
              'interconnect': interconnect, 'soc': soc, 'pmic': pmic, 'ufs-phy': ufs_phy, 'ipc': ipc,
              'remoteproc': remoteproc}
    parser.add_argument('group', choices=groups)
    args = parser.parse_args()
    raise SystemExit(groups[args.group]())
