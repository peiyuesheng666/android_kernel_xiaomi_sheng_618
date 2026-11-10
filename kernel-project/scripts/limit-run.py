#!/usr/bin/env python3
"""Limit the whole process group on cgroup-v2 Linux, including non-systemd WSL."""
import json
import os
from pathlib import Path
import subprocess
import sys

mount = Path('/sys/fs/cgroup')
controllers = {'memory', 'cpu'}
if not controllers <= set((mount / 'cgroup.controllers').read_text().split()):
    raise SystemExit('cgroup v2 memory/cpu controllers are required')
# Use an owned leaf; never change limits on the user's existing process group.
group = mount / ('sheng618-' + str(os.getpid()))
try:
    enabled = set((mount / 'cgroup.subtree_control').read_text().split())
    missing = controllers - enabled
    if missing:
        (mount / 'cgroup.subtree_control').write_text(' '.join('+' + c for c in sorted(missing)))
    group.mkdir()
    for name, value in {'memory.max': str(12 * 1024**3), 'memory.high': str(10 * 1024**3),
                        'memory.swap.max': str(1024**3), 'cpu.max': '400000 100000',
                        'memory.oom.group': '1'}.items():
        (group / name).write_text(value)
except PermissionError:
    raise SystemExit('Run as root or delegate a cgroup-v2 subtree to this account')

def enter():
    (group / 'cgroup.procs').write_text(str(os.getpid()))

try:
    values = {name: (group / name).read_text().strip()
              for name in ('memory.max', 'memory.high', 'memory.swap.max', 'cpu.max')}
    print('Verified resource limits: ' + json.dumps(values), flush=True)
    child = subprocess.Popen(sys.argv[1:], env={**os.environ, 'K618_LIMITS_VERIFIED': '1'},
                             preexec_fn=enter)
    try:
        code = child.wait()
    except KeyboardInterrupt:
        (group / 'cgroup.kill').write_text('1')
        child.wait()
        code = 130
    raise SystemExit(code)
finally:
    if group.exists() and not (group / 'cgroup.procs').read_text().strip():
        group.rmdir()
