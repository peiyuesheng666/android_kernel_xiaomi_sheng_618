#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Migrate pinned LOS Kalama platform drivers into isolated ACK external modules."""
import argparse
from kernel618_portlib import Port, ROOT, replace, void_remove


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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    groups = {'clocks': clocks, 'firmware': firmware, 'pinctrl': pinctrl, 'rpmh': rpmh,
              'interconnect': interconnect, 'soc': soc}
    parser.add_argument('group', choices=groups)
    args = parser.parse_args()
    raise SystemExit(groups[args.group]())
