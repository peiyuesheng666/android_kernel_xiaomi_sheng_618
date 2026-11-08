#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pinned LOS UFS/ICE migrations using the real ACK 6.18 core ABI."""
import re

from kernel618_portlib import Port, ROOT, replace, void_remove


def crypto():
    port = Port('crypto')
    names = ['crypto-qti-common.c', 'crypto-qti-hwkm.c', 'hwkm.c',
             'crypto-qti-ice-regs.h', 'crypto-qti-platform.h', 'hwkmregs.h', 'hwkm_serialize.h']
    for name in names:
        def transform(text):
            text = text.replace('key->raw', 'key->bytes')
            text = text.replace('#include <stdbool.h>', '#include <linux/types.h>')
            text = text.replace('#include <stddef.h>', '#include <linux/stddef.h>')
            if name == 'crypto-qti-common.c':
                text = replace(text, '#include <linux/genhd.h>\n', '')
                text = replace(text, '#include <linux/qseecom_kernel.h>',
                               '#include <linux/delay.h>\n#if IS_ENABLED(CONFIG_QTI_CRYPTO_FDE)\n'
                               '#include <linux/qseecom_kernel.h>\n#endif')
                # These register dumps supply numbers, not a function-name argument.
                text = text.replace('pr_err("%s: ICE ', 'pr_err("ICE ')
                text = text.replace('pr_err("%s: ICE_STM', 'pr_err("ICE_STM')
                # Two mutually exclusive FDE/proxy definitions share this callback.
                text = text.replace('static int crypto_qti_ice_remove(', 'static void crypto_qti_ice_remove(')
                for start in list(re.finditer(r'static void crypto_qti_ice_remove\(', text))[::-1]:
                    end = text.index('\n}', start.start())
                    chunk = text[start.start():end].replace('return 0;', 'return;')
                    text = text[:start.start()] + chunk + text[end:]
            if name == 'crypto-qti-hwkm.c':
                # The upstream error path prints wrapped key material. Never log keys.
                start = text.index('static void print_key(')
                end = text.index('static int crypto_qti_program_hwkm_tz(', start)
                text = text[:start] + text[end:]
                text = replace(text, '\t\tprint_key(key, slot);\n', '')
                text = replace(text, 'int crypto_qti_get_hwkm_raw_secret_tz(',
                               'static int crypto_qti_get_hwkm_raw_secret_tz(')
            if name == 'hwkm.c':
                text = replace(text, '#include <linux/module.h>',
                               '#include <linux/module.h>\n#include <linux/delay.h>')
            return text
        port.copy('lineage-kernel', 'drivers/soc/qcom/' + name, name, transform)
    for name in ['crypto-qti-common.h', 'hwkm.h', 'tme_hwkm_master_defs.h', 'tme_hwkm_master.h', 'tmelog.h', 'mailbox/qmp.h']:
        def header(text):
            text = text.replace('#include <stdbool.h>\n', '').replace('#include <stddef.h>', '#include <linux/stddef.h>')
            if name == 'crypto-qti-common.h':
                text = replace(text, 'int crypto_qti_enable(void *mmio_data);',
                               'int crypto_qti_enable(void *mmio_data);\nint crypto_qti_resume(void *mmio_data);')
            return text
        port.copy('lineage-kernel', 'include/linux/' + name, transform=header)
    for path in sorted((ROOT / 'src/lineage-kernel/drivers/soc/qcom/tmecom').glob('*')):
        if path.suffix not in ('.c', '.h'):
            continue
        def tme(text):
            text = text.replace('#include <stdbool.h>', '#include <linux/types.h>')
            text = text.replace('#include <stddef.h>', '#include <linux/stddef.h>')
            text = text.replace('invalid length: %u, %u', 'invalid length: %zu, %zu')
            text = text.replace('response_len, sizeof(response)', 'response_len, sizeof(*response)')
            text = text.replace('request_size: %#x, response_size: %#x', 'request_size: %#zx, response_size: %#zx')
            if path.name == 'tme_hwkm_master.c':
                text = replace(text, '#include <linux/kernel.h>',
                               '#include <linux/kernel.h>\n#include <linux/tme_hwkm_master.h>')
            for callback in re.findall(r'\.remove\s*=\s*(\w+)', text):
                text = void_remove(text, callback)
            return text
        port.copy('lineage-kernel', path.relative_to(ROOT / 'src/lineage-kernel').as_posix(), path.name, tme)
    port.write('Kbuild', '# SPDX-License-Identifier: GPL-2.0-only\n'
               'LINUXINCLUDE := -I$(src)/include -I$(src)/../firmware/include $(LINUXINCLUDE)\n'
               'ccflags-y += -I$(src) -DCONFIG_QCOM_SCM_MODULE=1 -DCONFIG_QTI_CRYPTO_COMMON_MODULE=1 '
               '-DCONFIG_QTI_HW_KEY_MANAGER_MODULE=1 -DCONFIG_MSM_TMECOM_QMP_MODULE=1 -ferror-limit=0\n'
               'obj-m += crypto-qti-common.o crypto-qti-hwkm.o hwkm.o tmecom-intf.o\n'
               'tmecom-intf-y := tmecom.o tme_hwkm_master.o tmelog.o\n')
    port.finish(['crypto-qti-common.ko', 'crypto-qti-hwkm.ko', 'hwkm.ko', 'tmecom-intf.ko'],
                ['Uses the sheng HWKM configuration, not the legacy FDE/QSEECOM path.',
                 'Secure-world key protocols and encrypted userdata require physical validation.'])
    return port.build(['firmware'])


def host_header(text):
    text = replace(text, '#include "ufshcd.h"',
                   '#include "ufshcd.h"\n#include "sheng-ufs-private.h"')
    text = replace(text, '#define UFS_DEVICE_QUIRK_PA_HIBER8TIME          (1 << 15)',
                   '/* Use the canonical ACK PA_HIBER8TIME bit from ufs_quirks.h. */')
    # All four functions and all three host rail fields are private to this driver.
    text = text.replace('struct ufs_vreg', 'struct sheng_ufs_vreg')
    start = text.index('/**\n * ufshcd_dme_rmw')
    end = text.index('/*\n *  IOCTL opcode', start)
    text = text[:start] + text[end:]
    text = text.replace('current->cpu', 'task_cpu(current)')
    return text


def host_source(text):
    text = replace(text, '#include <linux/acpi.h>',
                   '#include <linux/acpi.h>\n#include <linux/delay.h>\n#include "ufshcd-priv.h"')
    text = text.replace('struct ufs_vreg', 'struct sheng_ufs_vreg')
    text = text.replace('current->cpu', 'task_cpu(current)')
    text = text.replace('ufshcd_get_local_unipro_ver(', 'sheng_get_local_unipro_ver(')
    text = replace(text, 'hba->host->hostt->rpm_autosuspend_delay', 'hba->host->rpm_autosuspend_delay')
    text = replace(text, 'ufs_is_valid_unit_desc_lun(&hba->dev_info, lun, 0)',
                   'ufs_is_valid_unit_desc_lun(&hba->dev_info, lun)')
    text = replace(text, 'ufshcd_hold(hba, false)', 'ufshcd_hold(hba)')
    text = replace(text, 'hba->host->host_blocked,', 'atomic_read(&hba->host->host_blocked),')
    start = text.index('\t/* Provide SCSI host ioctl API */')
    end = text.index('#endif', start) + len('#endif')
    text = text[:start] + ('\terr = sheng_ufs_install_ioctl(hba);\n'
                          '\tif (err)\n\t\tgoto out_variant_clear;') + text[end:]
    text = replace(text, 'static int ufs_qcom_init(struct ufs_hba *hba)',
                   '#include "sheng-ufs-ioctl.inc"\n\nstatic int ufs_qcom_init(struct ufs_hba *hba)')
    text = text.replace('UFSHCD_QUIRK_CUSTOM_KEYSLOT_MANAGER', 'UFSHCD_QUIRK_CUSTOM_CRYPTO_PROFILE')
    text = replace(text, '\tufshcd_qti_hba_init_crypto_capabilities(hba);',
                   '\terr = ufshcd_qti_hba_init_crypto_capabilities(hba);\n'
                   '\tif (err)\n\t\tgoto out_variant_clear;')
    text = replace(text, '\t.program_key\t\t= ufs_qcom_ice_program_key,\n', '')
    text = replace(text, 'bool scale_up, enum ufs_notify_change_status status)',
                   'bool scale_up, unsigned long target_freq, enum ufs_notify_change_status status)')
    text = replace(text, '\t\t\t\tstruct ufs_pa_layer_attr *dev_max_params,\n', '')
    # Negotiation now happens before TX equalization; PRE_CHANGE must not
    # overwrite a lower gear selected by clock scaling with the device maximum.
    start = text.index('\t\tufs_qcom_cap.hs_rx_gear =', text.index('static int ufs_qcom_pwr_change_notify('))
    end = text.index('\t\t/* enable the device ref clock', start)
    negotiation = text[start:end]
    negotiation = negotiation[:negotiation.index('\t\tif (ret) {')]
    negotiation = negotiation.replace('\t\t', '\t').replace('ret = ufs_qcom_get_pwr_dev_param', 'return ufs_qcom_get_pwr_dev_param')
    helper = ('static int ufs_qcom_negotiate_pwr_mode(struct ufs_hba *hba,\n'
              '\t\tconst struct ufs_pa_layer_attr *dev_max_params,\n'
              '\t\tstruct ufs_pa_layer_attr *dev_req_params)\n{\n'
              '\tstruct ufs_qcom_host *host = ufshcd_get_variant(hba);\n'
              '\tstruct ufs_qcom_dev_params ufs_qcom_cap;\n\n' + negotiation + '}\n\n')
    text = text[:start] + text[end:]
    text = replace(text, 'struct ufs_qcom_dev_params ufs_qcom_cap;\n', '')
    text = replace(text, 'static int ufs_qcom_pwr_change_notify(', helper + 'static int ufs_qcom_pwr_change_notify(')
    text = replace(text, '\t.pwr_change_notify\t= ufs_qcom_pwr_change_notify,',
                   '\t.negotiate_pwr_mode = ufs_qcom_negotiate_pwr_mode,\n'
                   '\t.pwr_change_notify\t= ufs_qcom_pwr_change_notify,')
    pos = text.index('static int ufs_qcom_get_pwr_dev_param(')
    end = text.index('\n{', pos)
    chunk = text[pos:end].replace('struct ufs_pa_layer_attr *dev_max', 'const struct ufs_pa_layer_attr *dev_max')
    text = text[:pos] + chunk + text[end:]
    text, n = re.subn(r'(static void ufs_qcom_config_scaling_param\([^)]*)void \*data\)',
                      r'\1struct devfreq_simple_ondemand_data *data)', text)
    if n != 2:
        raise RuntimeError(f'UFS scaling callback count changed: {n}')
    text = replace(text, '\tstatic struct devfreq_simple_ondemand_data *d;',
                   '\tstruct devfreq_simple_ondemand_data *d;')
    text = replace(text, 'struct ufs_dev_fix ufs_qcom_dev_fixups[]',
                   'struct ufs_dev_quirk ufs_qcom_dev_fixups[]')
    text, n = re.subn(r'UFS_FIX\((UFS_VENDOR_\w+), (UFS_ANY_MODEL),\s*([^)]+)\)',
                      r'{ .wmanufacturerid = \1, .model = \2, .quirk = \3 }', text)
    if n != 5:
        raise RuntimeError(f'UFS fixup count changed: {n}')
    text = replace(text, '\t{ .wmanufacturerid = UFS_VENDOR_TOSHIBA, .model = UFS_ANY_MODEL, .quirk = UFS_DEVICE_QUIRK_DELAY_AFTER_LPM },\n', '')
    text = replace(text, '\tufshcd_fixup_dev_quirks(hba, ufs_qcom_dev_fixups);',
                   '\tufshcd_fixup_dev_quirks(hba, ufs_qcom_dev_fixups);\n'
                   '\t/* ACK handles the post-VCC-off delay in its core regulator path. */\n'
                   '\tif (hba->dev_info.wmanufacturerid == UFS_VENDOR_TOSHIBA)\n'
                   '\t\thba->vcc_off_delay_us = max(hba->vcc_off_delay_us, 5000U);')
    text = replace(text, '\tEND_FIX', '\t{}')
    # ACK's WL driver performs the device shutdown before the platform callback.
    text = replace(text, '\tufshcd_pltfrm_shutdown(pdev);',
                   '\t/* ACK ufshcd_wl_shutdown already shut down the child UFS device. */')
    text = void_remove(text, 'ufs_qcom_remove')
    text = replace(text, 'struct uic_command *ucmd,', 'const struct uic_command *ucmd,')
    # REQ_HIPRI was a polling flag. Do not add REQ_POLLED after queue allocation;
    # retain vendor priority tuning without turning interrupt requests into polled I/O.
    text = replace(text, 'rq->cmd_flags |= REQ_HIPRI;', 'rq->cmd_flags |= REQ_PRIO;')
    # Historical interrupt fields no longer exist in ACK. Report the real current
    # interrupt status explicitly instead of fabricating a historical timestamp.
    text = replace(text, '\tdev_err(hba->dev, "last intr at %lld us, last intr status=0x%x\\n",\n'
                   '\t\tktime_to_us(hba->ufs_stats.last_intr_ts),\n\t\thba->ufs_stats.last_intr_status);',
                   '\tdev_err(hba->dev, "current intr status=0x%x (historical timestamp unavailable)\\n",\n'
                   '\t\tufshcd_readl(hba, REG_INTERRUPT_STATUS));')
    fixes = [
        ('freq_val=%u,cth=%u', 'freq_val=%u,cth=%lu'),
        ('mask: 0x%08x | assoc-qos-req: 0x%08x', 'mask: %*pbl | assoc-qos-req: %p'),
        ('__func__, cpu, qcg->mask, qos_req', '__func__, cpu, cpumask_pr_args(&qcg->mask), qos_req'),
        ('ab: %llu ib: %llu', 'ab: %u ib: %u'),
        ('ab: %llu ib:%llu', 'ab: %u ib:%u'),
        ('Error: failed setting (%s) bus vote', 'Error: %d failed setting (%s) bus vote'),
        ('Error: (%d) failed getting %s path', 'Error: (%ld) failed getting %s path'),
        ('qcg: 0x%08x', 'qcg: %p'), ('qos_req: 0x%08x', 'qos_req: %p'),
        ('Mask: 0x%08x', 'Mask: %*pbl'), ('mask: 0x%08x', 'mask: %*pbl'),
        ('__func__, qcg, qcg->mask', '__func__, qcg, cpumask_pr_args(&qcg->mask)'),
        ('Failed cpufreq policy,cpu=%d,mask=0x%08x', '%s: Failed cpufreq policy,cpu=%d,mask=%*pbl'),
        ('__func__, cpu, qcg->mask', '__func__, cpu, cpumask_pr_args(&qcg->mask)'),
        ('Invalid UFS thermal state (%d)', 'Invalid UFS thermal state (%lu)'),
        ('sizeof(md_entry.name), "%s_%d"', 'sizeof(md_entry.name), "%s_%llu"'),
        ('Thermal mitigation registration failed: %d', 'Thermal mitigation registration failed: %ld'),
        ('total %llu PA error', 'total %u PA error'),
    ]
    for old, new in fixes:
        if old not in text:
            raise RuntimeError(f'Expected UFS logging expression: {old}')
        text = text.replace(old, new)
    text = hook_lifecycle(text)
    return text


def hook_lifecycle(text):
    # Register global hooks once for the module, never once per probe/defer.
    hooks = [('send_command', 'ufs_qcom_hook_send_command'),
             ('compl_command', 'ufs_qcom_hook_compl_command'),
             ('send_uic_command', 'ufs_qcom_hook_send_uic_command'),
             ('send_tm_command', 'ufs_qcom_hook_send_tm_command'),
             ('check_int_errors', 'ufs_qcom_hook_check_int_errors'),
             ('update_sdev', 'ufs_qcom_update_sdev'),
             ('prepare_command', 'ufs_qcom_hook_prepare_command')]
    for hook, function in hooks:
        if hook in ('send_tm_command', 'prepare_command'):
            continue  # Empty/disabled for the sheng non-FDE configuration.
        start = text.index('static void ' + function + '(')
        end = text.index('\n}', start)
        chunk = text[start:end]
        if hook == 'update_sdev':
            chunk = replace(chunk, '\tsdev->broken_fua = 1;',
                            '\tstruct ufs_hba *hba = shost_priv(sdev->host);\n\n'
                            '\tif (hba->vops == &ufs_hba_qcom_vops && ufshcd_get_variant(hba))\n'
                            '\t\tsdev->broken_fua = 1;')
        else:
            pos = chunk.index('\n\n', chunk.index('struct ufs_qcom_host *host'))
            chunk = chunk[:pos] + ('\n\n\tif (hba->vops != &ufs_hba_qcom_vops || !host)\n'
                                   '\t\treturn;') + chunk[pos:]
        text = text[:start] + chunk + text[end:]
    start = text.index('static void ufs_qcom_register_hooks(void)')
    end = text.index('\n}', start) + 2
    register = ['static int ufs_qcom_register_hooks(void)\n{\n\tint ret;\n']
    for i, (hook, function) in enumerate(hooks):
        register.append(f'\tret = register_trace_android_vh_ufs_{hook}({function}, NULL);\n'
                        f'\tif (ret)\n\t\tgoto fail_{i};\n')
    register.append('\treturn 0;\n')
    for i in reversed(range(len(hooks))):
        register.append(f'fail_{i}:\n')
        if i:
            hook, function = hooks[i - 1]
            register.append(f'\tunregister_trace_android_vh_ufs_{hook}({function}, NULL);\n')
    register.append('\ttracepoint_synchronize_unregister();\n\treturn ret;\n}\n'
                    'static void ufs_qcom_unregister_hooks(void)\n{\n')
    for hook, function in reversed(hooks):
        register.append(f'\tunregister_trace_android_vh_ufs_{hook}({function}, NULL);\n')
    register.append('\ttracepoint_synchronize_unregister();\n}\n')
    text = text[:start] + ''.join(register) + text[end:]
    text = replace(text, '\tif (!(of_property_read_bool(np, "secondary-storage")))\n'
                   '\t\tufs_qcom_register_hooks();\n', '')
    text = replace(text, 'module_platform_driver(ufs_qcom_pltform);', '''static int __init sheng_ufs_init(void)
{
	int ret = ufs_qcom_register_hooks();

	if (ret)
		return ret;
	ret = platform_driver_register(&ufs_qcom_pltform);
	if (ret)
		ufs_qcom_unregister_hooks();
	return ret;
}
module_init(sheng_ufs_init);

static void __exit sheng_ufs_exit(void)
{
	platform_driver_unregister(&ufs_qcom_pltform);
	ufs_qcom_unregister_hooks();
}
module_exit(sheng_ufs_exit);''')
    return text


def crypto_profile(text):
    text = replace(text, '#include <crypto/algapi.h>',
                   '#include <crypto/algapi.h>\n#include <linux/blk-crypto-profile.h>')
    for old, new in [('blk_keyslot_manager', 'blk_crypto_profile'),
                     ('container_of(ksm, struct ufs_hba, ksm)', 'container_of(ksm, struct ufs_hba, crypto_profile)'),
                     ('hba->ksm', 'hba->crypto_profile'), ('devm_blk_ksm_init', 'devm_blk_crypto_profile_init'),
                     ('blk_ksm_ll_ops', 'blk_crypto_ll_ops'), ('.ksm_ll_ops', '.ll_ops'),
                     ('.crypto_modes_supported', '.modes_supported'),
                     ('.features = BLK_CRYPTO_FEATURE_WRAPPED_KEYS',
                      '.key_types_supported = BLK_CRYPTO_KEY_TYPE_HW_WRAPPED')]:
        text = text.replace(old, new)
    # hold() now synchronously ensures clocks are available and returns void.
    text, n = re.subn(r'\terr = ufshcd_hold\(hba, false\);\n\tif \(err\) \{\n'
                      r'\t\tpr_err\([^\n]+\n\t\t(?:goto out|return err);\n\t\}',
                      '\tufshcd_hold(hba);', text)
    if n != 3:
        raise RuntimeError(f'UFS crypto hold sites changed: {n}')
    text = replace(text, '\nout:\n\n\treturn err;', '\n\treturn err;')
    text = replace(text, '\tif (!key) {',
                   '\tif (!key || key->crypto_cfg.crypto_mode != BLK_ENCRYPTION_MODE_AES_256_XTS ||\n'
                   '\t    key->crypto_cfg.key_type != BLK_CRYPTO_KEY_TYPE_HW_WRAPPED ||\n'
                   '\t    key->size <= RAW_SECRET_SIZE || key->size > sizeof(key->bytes) ||\n'
                   '\t    key->crypto_cfg.data_unit_size < MINIMUM_DUN_SIZE ||\n'
                   '\t    key->crypto_cfg.data_unit_size > MAXIMUM_DUN_SIZE ||\n'
                   '\t    !is_power_of_2(key->crypto_cfg.data_unit_size)) {')
    text = replace(text, '\t\t\t\t\t       unsigned int wrapped_key_size,\n'
                   '\t\t\t\t\t       u8 *secret,\n'
                   '\t\t\t\t\t       unsigned int secret_size)',
                   '\t\t\t\t\t       size_t wrapped_key_size,\n'
                   '\t\t\t\t\t       u8 secret[BLK_CRYPTO_SW_SECRET_SIZE])')
    text = replace(text, '\t\t\t\tsecret, secret_size);',
                   '\t\t\t\tsecret, BLK_CRYPTO_SW_SECRET_SIZE);')
    text = replace(text, '\t.derive_raw_secret\t=', '\t.derive_sw_secret\t=')
    start = text.index('static int ufshcd_crypto_qti_derive_raw_secret(')
    pos = text.index('\n\tif (host->reset_in_progress)', start)
    text = text[:pos] + ('\n\tif (wrapped_key_size <= RAW_SECRET_SIZE ||\n'
                         '\t    wrapped_key_size > BLK_CRYPTO_MAX_HW_WRAPPED_KEY_SIZE)\n'
                         '\t\treturn -EINVAL;\n') + text[pos:]
    return text


def host():
    port = Port('ufs-host')
    for name in ['ufs-qcom.c', 'ufs-qcom.h', 'ufs-qcom-trace.h', 'ufs-qcom-ice.c',
                 'ufshcd-crypto-qti.c', 'ufshcd-crypto-qti.h']:
        def transform(text):
            if name == 'ufs-qcom.h':
                return host_header(text)
            if name == 'ufs-qcom.c':
                return host_source(text)
            if name == 'ufshcd-crypto-qti.c':
                return crypto_profile(text)
            if name == 'ufs-qcom-ice.c':
                text = text.replace('UFSHCD_QUIRK_CUSTOM_KEYSLOT_MANAGER', 'UFSHCD_QUIRK_CUSTOM_CRYPTO_PROFILE')
                # Allocate only after the no-key eviction and capability checks.
                allocation = ('\terr = qtee_shmbridge_allocate_shm(AES_256_XTS_KEY_SIZE, &shm);\n'
                              '\tif (err)\n\t\treturn -ENOMEM;\n\n')
                text = replace(text, allocation, '')
                text = replace(text, '\tmemcpy(key.bytes, cfg->crypto_key, AES_256_XTS_KEY_SIZE);',
                               allocation + '\tmemcpy(key.bytes, cfg->crypto_key, AES_256_XTS_KEY_SIZE);')
            if name == 'ufs-qcom-trace.h':
                text = re.sub(r'__assign_str\((\w+), [^;]+\);', r'__assign_str(\1);', text)
                text = re.sub(r'#define TRACE_INCLUDE_PATH [^\n]+', '#define TRACE_INCLUDE_PATH .', text)
                text = replace(text, 'dev_pwr_mode = %d, err = %d', 'dev_pwr_mode = %s, err = %d')
            return text
        port.copy('lineage-kernel', 'drivers/scsi/ufs/' + name, name, transform)
    for name in ['ufshcd.h', 'unipro.h', 'ufshci.h', 'ufs_quirks.h']:
        port.write(name, '#include <ufs/' + name + '>\n')
    for folder, name in [('host', 'ufshcd-pltfrm.h'), ('core', 'ufshcd-crypto.h'), ('core', 'ufshcd-priv.h')]:
        port.copy('ack', 'drivers/ufs/' + folder + '/' + name, name)
    def private(text):
        start = text.index('enum ufs_trace_str_t {')
        return text[start:text.index('};', start) + 2] + '\n'
    port.copy('lineage-kernel', 'drivers/scsi/ufs/ufs.h', 'sheng-ufs-trace-enum.h', private)
    def local_unipro(text):
        start = text.index('u32 ufshcd_get_local_unipro_ver(')
        end = text.index('\nEXPORT_SYMBOL(', start)
        return text[start:end].replace('u32 ufshcd_get_local_unipro_ver', 'static inline u32 sheng_get_local_unipro_ver')
    port.copy('lineage-kernel', 'drivers/scsi/ufs/ufshcd.c', 'sheng-ufs-unipro.h', local_unipro)
    def private_vreg(text):
        start = text.index('struct ufs_vreg {')
        return text[start:text.index('};', start) + 2].replace('struct ufs_vreg', 'struct sheng_ufs_vreg') + '\n'
    port.copy('lineage-kernel', 'drivers/scsi/ufs/ufs.h', 'sheng-ufs-vreg.h', private_vreg)
    port.write('sheng-ufs-private.h', '#ifndef SHENG_UFS_PRIVATE_H\n#define SHENG_UFS_PRIVATE_H\n'
               '#include <ufs/ufs_quirks.h>\n#include "sheng-ufs-trace-enum.h"\n'
               '#include "sheng-ufs-unipro.h"\n#include "sheng-ufs-vreg.h"\n#endif\n')
    port.write('sheng-ufs-ioctl.inc', '''/* SPDX-License-Identifier: GPL-2.0-only */
/* Static storage outlives all SCSI host references, including failed probes. */
static DEFINE_MUTEX(sheng_ufs_sht_lock);
static struct scsi_host_template sheng_ufs_sht;
static const struct scsi_host_template *sheng_ufs_original_sht;

static int sheng_ufs_install_ioctl(struct ufs_hba *hba)
{
	int ret = 0;

	mutex_lock(&sheng_ufs_sht_lock);
	if (!sheng_ufs_original_sht) {
		sheng_ufs_sht = *hba->host->hostt;
		sheng_ufs_sht.ioctl = ufs_qcom_ioctl;
#ifdef CONFIG_COMPAT
		sheng_ufs_sht.compat_ioctl = ufs_qcom_ioctl;
#endif
		sheng_ufs_original_sht = hba->host->hostt;
	} else if (hba->host->hostt != sheng_ufs_original_sht &&
		   hba->host->hostt != &sheng_ufs_sht) {
		ret = -EINVAL;
		goto out;
	}
	hba->host->hostt = &sheng_ufs_sht;
out:
	mutex_unlock(&sheng_ufs_sht_lock);
	return ret;
}
''')
    port.copy('lineage-kernel', 'include/linux/crypto-qti-common.h')
    port.copy('lineage-kernel', 'include/linux/clk/qcom.h')
    port.write('Kbuild', '# SPDX-License-Identifier: GPL-2.0-only\n'
               'LINUXINCLUDE := -I$(src)/include -I$(src)/../firmware/include -I$(src)/../ufs-phy/include '
               '-I$(src)/../rpmh/include $(LINUXINCLUDE)\n'
               'ccflags-y += -I$(src) -DCONFIG_IPC_LOGGING=1 -DCONFIG_QCOM_SCM_MODULE=1 '
               '-DCONFIG_QTI_CRYPTO_COMMON_MODULE=1 -DCONFIG_QTI_HW_KEY_MANAGER_MODULE=1 '
               '-DCONFIG_SCSI_UFS_CRYPTO_QTI_MODULE=1 -ferror-limit=0\n'
               'obj-m += ufs_qcom.o ufshcd-crypto-qti.o\n'
               'ufs_qcom-y := ufs-qcom.o ufs-qcom-ice.o\n')
    port.finish(['ufs_qcom.ko', 'ufshcd-crypto-qti.ko'],
                ['Static build and ABI checks only; not a validated storage boot candidate.',
                 'Wrapped-key program/evict/derive use LOS SCM/HWKM. New block import/generate/prepare operations are not available.',
                 'Stock fscrypt/dm wrapped-key userspace ABI still needs independent compatibility work for both ROMs.',
                 'Historical interrupt timestamps are unavailable; the dump reports current interrupt status.',
                 'Legacy REQ_HIPRI polling mutation becomes REQ_PRIO without changing request completion mode.',
                 'Full minidump and complete probe/remove fault-injection validation remain outstanding.'])
    return port.build(['ufs-phy', 'rpmh', 'clock-los', 'firmware', 'crypto'])
