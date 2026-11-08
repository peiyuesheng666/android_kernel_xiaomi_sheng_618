#!/usr/bin/env python3
"""Validate and assemble only the device init permission correction; no Ninja graph."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from audit_upstream_sources import inspect

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
PRODUCT = ROM / 'out/target/product/sheng'
HOST = ROM / 'out/host/linux-x86/bin'
DIAG = Path('/root/sheng-lineage/hardware-diagnostics')
BASE_RC = '021e9c5be5871089c51ae1ba62ab42a0e7b97e9cef064d75d11244c8e75956de'


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
    assert all(r['passed'] and r['fetch']['returncode'] == 0 for r in audit['repositories'])
    assert args.work.parent.resolve() == DIAG and not args.work.exists()
    args.work.mkdir()
    extras = ['system/core', 'build/make', 'hardware/lineage/interfaces']
    with ThreadPoolExecutor(max_workers=3) as executor:
        supplemental = list(executor.map(lambda r: inspect(ROM, r, True), extras))
    (args.work / 'supplemental-prebuild-audit.json').write_text(json.dumps(supplemental, indent=2) + '\n')
    assert all(r['passed'] for r in supplemental)
    rc = DEVICE / 'rootdir/etc/init.sm8550.rc'
    text = rc.read_text()
    added = ('    # This driver exposes class attributes without a matching device uevent.\n'
             '    # Grant access before the Lineage health HAL probes charging-control nodes;\n'
             '    # otherwise its constructor waits forever and blocks framework startup.\n'
             '    wait /sys/class/qcom-battery/input_suspend 10\n'
             '    chown system system /sys/class/qcom-battery/input_suspend\n'
             '    chmod 0660 /sys/class/qcom-battery/input_suspend\n\n')
    assert text.count(added) == 1 and 'on post-fs-data\n' + added in text
    baseline = text.replace(added, '', 1).encode()
    assert hashlib.sha256(baseline).hexdigest() == BASE_RC
    (args.work / 'baseline-init.sm8550.rc').write_bytes(baseline)
    source_hash = sha(rc)
    target = PRODUCT / 'vendor/etc/init/init.sm8550.rc'
    assert sha(target) == BASE_RC
    command = [str(HOST / 'host_init_verifier'), '-p', str(PRODUCT / 'vendor/etc/passwd'),
               '-p', str(PRODUCT / 'system/etc/passwd'),
               '--property-contexts=' + str(PRODUCT / 'vendor/etc/selinux/vendor_property_contexts'), str(rc)]
    result = subprocess.run(command, cwd=ROM, capture_output=True, text=True,
                            env=dict(os.environ, LD_LIBRARY_PATH=str(HOST.parent / 'lib64')))
    (args.work / 'commands.json').write_text(json.dumps([dict(command=command,
        returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)], indent=2) + '\n')
    assert result.returncode == 0, result.stderr
    assert sha(rc) == source_hash
    shutil.copyfile(rc, target)
    assert sha(target) == source_hash
    with ThreadPoolExecutor(max_workers=3) as executor:
        post = list(executor.map(lambda r: inspect(ROM, r, True), extras))
    (args.work / 'supplemental-postbuild-audit.json').write_text(json.dumps(post, indent=2) + '\n')
    assert all(r['passed'] for r in post)
    report = dict(revision=33, scoped_configuration_assembly_passed=True,
        host_init_verifier_passed=True, exact_seven_line_delta_verified=True,
        charging_value_written=False, supplemental_public_audit_passed=True,
        full_product_build_passed=False, normal_product_module_build_passed=False,
        source_sha256={'rootdir/etc/init.sm8550.rc': source_hash,
                       'tools/build_sheng_charging_boot_r33.py': sha(Path(__file__))},
        reviewed_sha256={'vendor': {'etc/init/init.sm8550.rc': source_hash}},
        baseline_rc_sha256=BASE_RC, prebuild_audit_sha256=sha(args.audit),
        command_log_sha256=sha(args.work / 'commands.json'), work=str(args.work),
        systemui_changed=False, installed=False, runtime_verified=False)
    path = args.work / 'build-result.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(path)


if __name__ == '__main__':
    main()
