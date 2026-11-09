#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Keep the selected 5.15 FastRPC provider on its real vendor APIs."""
from audit_kernel618_modules import ElfModule


REQUIRED_IMPORTS = (
    'mem_buf_dma_buf_exclusive_owner',
    'qcom_register_ssr_notifier',
    'msm_minidump_add_region',
    'qcom_elf_dump',
)
EVA_REQUIRED_IMPORTS = (
    'fastrpc_driver_register',
    'fastrpc_driver_unregister',
    'fastrpc_driver_invoke',
)


def build_flags(k618):
    soc = k618 / 'soc'
    config = k618 / 'tp-autoconf.h'
    if not config.is_file():
        raise ValueError('Missing FastRPC vendor configuration: ' + str(config))
    return [
        'NOSTDINC_FLAGS=-nostdinc -I' + str(soc / 'include') +
        ' -I' + str(soc / 'include/uapi'),
        'KCFLAGS=-include ' + str(config),
        'CONFIG_ARCH_KALAMA=y',
    ]


def verify_imports(module, required=REQUIRED_IMPORTS):
    parsed = ElfModule(module)
    # An ABI check cannot find a missing dependency after the compiler replaced
    # its API with a static inline stub. Require the actual external calls too.
    imported = parsed.undefined()
    missing = sorted(set(required) - imported)
    if missing:
        raise ValueError('FastRPC vendor APIs compiled as stubs: ' + ', '.join(missing))
    return dict(module=str(module), required_imports=list(required),
                vendor_api_imports_verified=True)
