#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reject old QMP binaries after applying the sheng pipe-parent repair."""
import hashlib
import json
from audit_kernel618_modules import ElfModule

REQUIRED_IMPORTS = ('__clk_get_hw', 'clk_has_parent', 'clk_hw_get_parent_by_index',
                    'devm_clk_hw_get_clk')


def verify(module, project, k618):
    receipt = project / 'reports/kernel618-ssphy-pipe-xo-source.json'
    if not receipt.is_file():
        return None
    source = json.loads(receipt.read_text())
    target = k618 / 'soc' / source['source']
    assert hashlib.sha256(target.read_bytes()).hexdigest() == source['after_sha256']
    gcc = k618 / 'soc/drivers/clk/qcom/gcc-kalama.c'
    assert hashlib.sha256(gcc.read_bytes()).hexdigest() == source['gcc_source_sha256']
    missing = sorted(set(REQUIRED_IMPORTS) - ElfModule(module).undefined())
    if missing:
        raise ValueError('QMP pipe-parent repair absent from ELF: ' + ', '.join(missing))
    return dict(module=str(module), required_imports=list(REQUIRED_IMPORTS),
                source_sha256=source['after_sha256'], actual_ccf_parent_api_imports_verified=True)
