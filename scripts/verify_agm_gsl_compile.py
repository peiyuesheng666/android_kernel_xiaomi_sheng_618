#!/usr/bin/env python3
"""Reproduce the real AGM compile with the restored exported GSL include paths."""
import json
import os
from pathlib import Path
import shlex
import subprocess

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
logs = rom.parent / 'logs'
failure = logs / 'failures/1b130450f2e34a44bc08efb17c9ec094.log'
lines = failure.read_text().splitlines()
command = None
for index, line in enumerate(lines):
    if line.startswith('FAILED: ') and line.endswith('/agm_server_wrapper.o'):
        command = shlex.split(lines[index + 1])
        break
assert command and command.pop(0) == 'PWD=/proc/self/cwd'
assert command[0] == '/usr/bin/ccache' and command[1].endswith('/clang++')
assert command[-1] == 'hardware/qcom-caf/sm8550/audio/agm/ipc/HwBinders/agm_ipc_service/src/agm_server_wrapper.cpp'
target = (rom / command[command.index('-o') + 1]).resolve()
assert target.is_relative_to(rom / 'out') and target.name == 'agm_server_wrapper.o'
for directory in ('api', 'dls_client_api', 'hw_rsc_api', 'rtc_api'):
    command.extend(['-I', f'hardware/qcom-caf/sm8550/audio/graphservices/gsl/{directory}'])
environment = dict(os.environ, PWD='/proc/self/cwd', CCACHE_DIR='/root/sheng-lineage/ccache')
logfile = logs / 'verify-agm-gsl.log'
with logfile.open('w') as output:
    result = subprocess.run(command, cwd=rom, env=environment, stdout=output, stderr=subprocess.STDOUT)
report = {'real_agm_compile_passed': result.returncode == 0, 'returncode': result.returncode,
          'log': str(logfile), 'soong_export_propagation': 'pending current validation run'}
(work / 'reports/agm-gsl-compile.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
raise SystemExit(result.returncode)
