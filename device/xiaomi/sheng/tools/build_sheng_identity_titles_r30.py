#!/usr/bin/env python3
"""Rebuild only the Settings identity overlay for the r30 title-color correction."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
OUT = Path('/root/sheng-lineage/hardware-diagnostics/r30-identity-title-build')
PRE = OUT.parent / 'r30-prebuild-audit-20261108.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert DEVICE == ROM / 'device/xiaomi/sheng'
    audit = json.loads(PRE.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert all(r['fetch']['returncode'] == 0 for r in audit['repositories'])
    OUT.mkdir(exist_ok=False)
    original = OUT.parent / 'r29-identity-boot-build-attempt3'
    original_commands = original / 'commands.json'
    previous_review = json.loads((DEVICE / 'docs/r29-identity-boot-build-review-20261108.json').read_text())
    assert sha(original_commands) == previous_review['command_log_sha256']
    jdk = ROM / 'prebuilts/jdk/jdk21/linux-x86'
    env = dict(os.environ, JAVA_HOME=str(jdk), PATH=str(jdk / 'bin') + ':' + os.environ['PATH'],
               LD_LIBRARY_PATH=str(ROM / 'out/host/linux-x86/lib64'))
    commands = []
    for entry in json.loads(original_commands.read_text()):
        command = entry['command']
        if Path(command[0]).name == 'host_init_verifier':
            continue  # The init RC is unchanged from the verified r29 installation.
        command = [part.replace(str(original), str(OUT)) for part in command]
        result = subprocess.run(command, cwd=ROM, env=env, capture_output=True, text=True)
        commands.append(dict(command=command, returncode=result.returncode,
                             stdout=result.stdout, stderr=result.stderr))
        (OUT / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        assert result.returncode == 0, result.stdout + result.stderr
    apk = OUT / 'SettingsResOverlaySheng.apk'
    target = ROM / 'out/target/product/sheng/odm/overlay/SettingsResOverlaySheng.apk'
    shutil.copyfile(apk, target)
    overlay = DEVICE / 'overlay/SettingsResOverlaySheng'
    sources = [*sorted(overlay.rglob('*.xml')), overlay / 'Android.bp',
               DEVICE / 'tools/tablet_probe/ResourceProbe.java', Path(__file__)]
    review = dict(revision=30, scoped_module_build_passed=True, full_product_build_passed=False,
                  host_idmap_overlayable_enforced=True, systemui_changed=False,
                  source_sha256={str(p.relative_to(DEVICE)): sha(p) for p in sources},
                  reviewed_sha256={'odm': {'overlay/SettingsResOverlaySheng.apk': sha(apk)}},
                  prebuild_audit_sha256=sha(PRE), command_log_sha256=sha(OUT / 'commands.json'),
                  source_command_log_sha256=sha(original_commands), installed=False, runtime_verified=False)
    path = DEVICE / 'docs/r30-identity-title-build-review-20261108.json'
    assert not path.exists()
    path.write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps(review, indent=2))


if __name__ == '__main__': main()
