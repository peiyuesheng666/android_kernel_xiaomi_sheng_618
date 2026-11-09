#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Apply and verify the user's policy for built-in GKI root components."""
import json
import re
import subprocess


def read_policy(project):
    path = project / 'device/xiaomi/sheng/interfaces/kernel/6.18/root-policy.json'
    return json.loads(path.read_text()) if path.is_file() else None


def configure(ack, output, project):
    policy = read_policy(project)
    if not policy or policy['built_in_gki_root']:
        return
    config = output / '.config'
    keys = set(re.findall(r'^(?:# )?(CONFIG_\w+)(?:=| is not set)', config.read_text(), re.M))
    prefixes = tuple('CONFIG_' + name for name in policy['disable_config_prefixes'])
    disabled = sorted(key for key in keys if any(
        key == prefix or key.startswith(prefix + '_') for prefix in prefixes))
    # Disable the top-level root option even if an upstream recipe deleted its
    # old config entry, so olddefconfig cannot pick an upstream default.
    disabled += [p for p in prefixes if p not in disabled]
    subprocess.run([ack / 'scripts/config', '--file', config,
                    *[arg for key in disabled for arg in ('--disable', key.removeprefix('CONFIG_'))]],
                   check=True)


def verify(output, project):
    policy = read_policy(project)
    if not policy or policy['built_in_gki_root']:
        return None
    active = re.findall(r'^(CONFIG_\w+)=[ym]$', (output / '.config').read_text(), re.M)
    prefixes = tuple('CONFIG_' + name for name in policy['disable_config_prefixes'])
    unwanted = [key for key in active if any(
        key == prefix or key.startswith(prefix + '_') for prefix in prefixes)]
    if unwanted:
        raise ValueError('Built-in root options still enabled: ' + ', '.join(unwanted))
    symbols = re.findall(r'^\S+\s+\S+\s+(\S+)$', (output / 'System.map').read_text(), re.M)
    unwanted_symbols = [name for name in symbols if name.startswith(('ksu_', 'susfs_'))]
    if unwanted_symbols:
        raise ValueError('Built-in root symbols remain: ' + ', '.join(unwanted_symbols[:12]))
    return dict(built_in_gki_root=False, disabled_prefixes=policy['disable_config_prefixes'],
                active_root_options=[], defined_root_symbols=[], verified=True)
