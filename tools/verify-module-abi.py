#!/usr/bin/env python3
"""Reject ARM64 module ABI mismatches before embedding or flashing a build."""
import json
from pathlib import Path
import sys
from audit_kernel618_modules import ElfModule, check_candidate

output = Path(sys.argv[1])
layer = Path(sys.argv[2])
modules = {path.name: ElfModule(path) for path in layer.glob('*.ko')}
assert len(modules) == 344
result = check_candidate(modules, {'source_keep_modules': ['zram.ko', 'zsmalloc.ko']}, output,
                         [layer / 'zram.ko', layer / 'zsmalloc.ko'], '6.18')
assert result['abi_passed'], result['issue_counts']
print(json.dumps(result, indent=2))
