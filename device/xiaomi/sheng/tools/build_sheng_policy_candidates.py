#!/usr/bin/env python3
"""Compile isolated device policy candidates using recorded Soong commands.

Never load the full Ninja graph or change installed product trees. Retain
neverallow checks and require the unchanged baseline to reproduce exactly.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
DIAGNOSTICS = Path('/root/sheng-lineage/hardware-diagnostics')
BASELINE = 'ccb422e37de241d4da50eb1ae8890cf1fe3fe895677658932b861d2de7e6471b'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--templates', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__ and DEVICE == ROM / 'device/xiaomi/sheng'
    audit = json.loads(args.audit.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert len(audit['repositories']) == 22 and audit['project_count'] == 1243
    assert all(v['passed'] and v['fetch']['returncode'] == 0 for v in audit['repositories'])
    work = args.work
    assert work.is_absolute() and work.parent.resolve(strict=True) == DIAGNOSTICS
    assert not work.exists()
    work.mkdir()
    templates = json.loads(args.templates.read_text())
    commands = []
    inputs = {}

    def remember(path):
        path = path if path.is_absolute() else ROM / path
        assert path.is_file(), str(path)
        inputs[str(path)] = sha(path)

    def run(command, output=None):
        command = list(map(str, command))
        if output is None:
            result = subprocess.run(command, cwd=ROM, text=True, capture_output=True)
        else:
            with output.open('w') as stream:
                result = subprocess.run(command, cwd=ROM, text=True, stdout=stream,
                                        stderr=subprocess.PIPE)
        commands.append(dict(command=command, returncode=result.returncode,
                             stdout=result.stdout, stderr=result.stderr,
                             output=str(output) if output else None))
        (work / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        assert result.returncode == 0, (command, result.stdout, result.stderr)

    def rule(name):
        lines = templates['rule m.' + name]
        assert len(lines) == 1 and lines[0].startswith('    command = ')
        return lines[0].split(' = ', 1)[1].split(' # hash of input list:', 1)[0]

    # A byte-identical baseline prevents silently dropping previous policy fixes.
    final = shlex.split(rule('precompiled_sepolicy_android_common.secilc').split(' && ', 1)[0])
    assert '-N' not in final
    for value in final:
        if value.endswith('.cil') or value == final[0]:
            remember(Path(value))
    final[final.index('-o') + 1] = str(work / 'baseline-precompiled_sepolicy')
    run(final)
    assert sha(work / 'baseline-precompiled_sepolicy') == BASELINE

    script = ROM / shlex.split(rule('vendor_sepolicy.conf_android_common.conf'))[0]
    remember(script)
    text = script.read_text()
    command = shlex.split(text.split(' && ', 1)[1].split(' > ', 1)[0])
    assert command[0] == 'prebuilts/build-tools/linux-x86/bin/m4'
    newline = 'out/soong/.intermediates/system/sepolicy/vendor_sepolicy.conf/android_common/newline'
    (work / 'newline').write_text('\n')
    command = [str(work / 'newline') if v == newline else v for v in command]
    listed = {v for v in command if v.startswith('device/xiaomi/sheng/sepolicy/')}
    actual = {str(p.relative_to(ROM)) for p in (DEVICE / 'sepolicy/vendor').glob('*.te')}
    added = sorted(actual - listed)
    assert added == ['device/xiaomi/sheng/sepolicy/vendor/hal_miface_default.te']
    position = max(i for i, value in enumerate(command) if value.endswith('.te')) + 1
    command[position:position] = [str(work / 'newline'), *added, str(work / 'newline')]
    for value in command:
        path = Path(value)
        if (path if path.is_absolute() else ROM / path).is_file():
            remember(path)
    conf = work / 'vendor_sepolicy.conf'
    run(command, conf)
    unversioned = work / 'vendor_sepolicy.unversioned.cil'
    run(['out/host/linux-x86/bin/checkpolicy', '-C', '-M', '-L', '-c', '30',
         '-o', unversioned, conf])
    mask = 'out/soong/.intermediates/system/sepolicy/reqd_policy_mask.cil/android_common/reqd_policy_mask.cil'
    public = 'out/soong/.intermediates/system/sepolicy/pub_policy.cil/android_common/sheng/pub_policy.cil'
    versioned = 'out/soong/.intermediates/system/sepolicy/plat_pub_versioned.cil/android_common/sheng/plat_pub_versioned.cil'
    for path in [mask, public, versioned]:
        remember(Path(path))
    run(['out/host/linux-x86/bin/build_sepolicy', 'filter_out', '-f', mask, '-t', unversioned])
    mapping, attributed = work / 'mapping.cil', work / 'attributed.cil'
    run(['out/host/linux-x86/bin/version_policy', '-b', public, '-n', '202604',
         '-o', mapping, '-m'])
    run(['out/host/linux-x86/bin/version_policy', '-b', public, '-n', '202604',
         '-t', unversioned, '-o', attributed])
    run(['out/host/linux-x86/bin/build_sepolicy', 'filter_out', '-f', mapping, '-t', attributed])
    vendor = work / 'vendor_sepolicy.cil'
    vendor.write_bytes(mapping.read_bytes() + attributed.read_bytes())
    run(['out/host/linux-x86/bin/build_sepolicy', 'filter_out', '-f', versioned, '-t', vendor])
    vendor_input = 'out/soong/.intermediates/system/sepolicy/vendor_sepolicy.cil/android_common/sheng/vendor_sepolicy.cil'
    assert final.count(vendor_input) == 1
    final[final.index(vendor_input)] = str(vendor)
    final[final.index('-o') + 1] = str(work / 'precompiled_sepolicy')
    run(final)

    # Context checks use the actual compiled candidate's type declarations.
    for filename, options in [('file_contexts', []), ('hwservice_contexts', ['-l'])]:
        path = DEVICE / 'sepolicy/vendor' / filename
        remember(path)
        run(['out/host/linux-x86/bin/checkfc', *options,
             work / 'precompiled_sepolicy', path])
    tests = work / 'face-file-context-tests.txt'
    tests.write_text('/odm/bin/hw/android.hardware.biometrics.face-aidl-service hal_face_default_exec\n'
                     '/vendor/odm/bin/hw/android.hardware.biometrics.face-aidl-service hal_face_default_exec\n'
                     '/odm/bin/mifaced@1.0 hal_miface_default_exec\n'
                     '/vendor/odm/bin/mifaced@1.0 hal_miface_default_exec\n')
    # checkfc -t also requires every supplied regex to have a test. The full
    # device context file was validated above; match-test the exact new subset.
    subset = work / 'face-file-contexts'
    entries = [line for line in (DEVICE / 'sepolicy/vendor/file_contexts').read_text().splitlines()
               if line.endswith(('u:object_r:hal_face_default_exec:s0',
                                 'u:object_r:hal_miface_default_exec:s0'))]
    assert len(entries) == 2
    subset.write_text('\n'.join(entries) + '\n')
    run(['out/host/linux-x86/bin/checkfc', '-t', subset, tests])
    outputs = {p.name: dict(path=str(p), sha256=sha(p), bytes=p.stat().st_size)
               for p in [vendor, work / 'precompiled_sepolicy']}
    report = dict(scoped_policy_build_passed=True, full_product_build_passed=False,
                  neverallow_checks_enabled=True, baseline_reproduced_sha256=BASELINE,
                  inputs_sha256=inputs, added_device_policy_sources=added, outputs=outputs,
                  audit_sha256=sha(args.audit), templates_sha256=sha(args.templates),
                  builder_sha256=sha(Path(__file__)), commands_sha256=sha(work / 'commands.json'),
                  installed=False, device_operated=False, camera_opened=False)
    (work / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
