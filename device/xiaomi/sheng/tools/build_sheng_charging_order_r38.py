#!/usr/bin/env python3
"""Verify and assemble the charging permission action after early-boot ADSP startup."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
PRODUCT = ROM / 'out/target/product/sheng'
HOST = ROM / 'out/host/linux-x86/bin'
BASE_RC = 'e95aff62e4d5b5d296707afaa150d2f61c6131b9c3eb2ee7cd1eddc44f9c41e4'
OLD = ('    # This driver exposes class attributes without a matching device uevent.\n'
       '    # Grant access before the Lineage health HAL probes charging-control nodes;\n'
       '    # otherwise its constructor waits forever and blocks framework startup.\n'
       '    wait /sys/class/qcom-battery/input_suspend 10\n'
       '    chown system system /sys/class/qcom-battery/input_suspend\n'
       '    chmod 0660 /sys/class/qcom-battery/input_suspend\n\n')
NEW = ('    # PMIC GLINK creates these class attributes after ADSP starts in early-boot.\n'
       '    # Waiting in post-fs-data can delay that startup and expire before creation.\n'
       '    # Set metadata before class hal starts; do not alter the charging value.\n'
       '    wait /sys/class/qcom-battery/input_suspend 10\n'
       '    chown system system /sys/class/qcom-battery/input_suspend\n'
       '    chmod 0660 /sys/class/qcom-battery/input_suspend\n\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__ and DEVICE == ROM / 'device/xiaomi/sheng'
    audit = json.loads(args.audit.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert len(audit['repositories']) == 28
    assert all(r['passed'] and r['fetch']['returncode'] == 0 for r in audit['repositories'])
    assert args.work.parent.resolve() == Path('/root/sheng-lineage/hardware-diagnostics')
    assert not args.work.exists()
    args.work.mkdir()
    rc = DEVICE / 'rootdir/etc/init.sm8550.rc'
    text = rc.read_text()
    assert text.count(NEW) == 1 and text.count('on boot\n' + NEW) == 1
    assert text.count('/sys/class/qcom-battery/input_suspend') == 3
    baseline = text.replace(NEW, '', 1).replace('on post-fs-data\n', 'on post-fs-data\n' + OLD, 1)
    assert hashlib.sha256(baseline.encode()).hexdigest() == BASE_RC
    (args.work / 'baseline-init.sm8550.rc').write_text(baseline)
    target = PRODUCT / 'vendor/etc/init/init.sm8550.rc'
    assert sha(target) == BASE_RC
    command = [str(HOST / 'host_init_verifier'), '-p', str(PRODUCT / 'vendor/etc/passwd'),
               '-p', str(PRODUCT / 'system/etc/passwd'),
               '--property-contexts=' + str(PRODUCT / 'vendor/etc/selinux/vendor_property_contexts'),
               str(rc)]
    result = subprocess.run(command, cwd=ROM, capture_output=True, text=True,
                            env=dict(os.environ, LD_LIBRARY_PATH=str(HOST.parent / 'lib64')))
    command_log = args.work / 'commands.json'
    command_log.write_text(json.dumps([dict(command=command, returncode=result.returncode,
                                           stdout=result.stdout, stderr=result.stderr)], indent=2) + '\n')
    assert result.returncode == 0, result.stderr
    source_hash = sha(rc)
    shutil.copyfile(rc, target)
    assert sha(target) == source_hash
    report = dict(revision=38, scoped_configuration_assembly_passed=True,
        host_init_verifier_passed=True, exact_action_move_verified=True,
        permission_commands_and_timeout_unchanged=True, charging_value_written=False,
        full_product_build_passed=False, normal_product_module_build_passed=False,
        prebuild_public_audit_passed=True, postbuild_public_audit_passed=False,
        public_repositories_fresh_audited=28, all_project_status_checked=audit['project_count'],
        source_sha256={p: sha(DEVICE / p) for p in (
            'rootdir/etc/init.sm8550.rc', 'tools/build_sheng_charging_order_r38.py')},
        reviewed_sha256={'vendor': {'etc/init/init.sm8550.rc': source_hash}},
        baseline_rc_sha256=BASE_RC, prebuild_audit_sha256=sha(args.audit),
        command_log_sha256=sha(command_log), work=str(args.work),
        systemui_changed=False, installed=False, runtime_verified=False)
    output = DEVICE / 'docs/r38-charging-order-build-review-20261108.json'
    assert not output.exists()
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    main()
