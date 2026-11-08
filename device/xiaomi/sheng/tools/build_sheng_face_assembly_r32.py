#!/usr/bin/env python3
"""Assemble the reviewed face/thermal payload without executing the Ninja graph.

Build the device matrix from its normal source inputs, check full live VINTF
metadata and kernel configuration, then update only declared build outputs.
This does not constitute a full product/module build or operate the device.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
PRODUCT = ROM / 'out/target/product/sheng'
DIAG = Path('/root/sheng-lineage/hardware-diagnostics')
GLOBAL_CONTEXTS = ROM / 'out/soong/.intermediates/system/sepolicy/file_contexts.concat.tmp/android_common/gen/file_contexts.concat.tmp'
MATRIX = 'etc/vintf/compatibility_matrix.device.xml'
MATRIX_BASELINE = '0ee417f7902898e885c3227f7a5690af3126d8eceed4c9083239c038bf0c464e'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(node):
    return node.tag, tuple(sorted(node.attrib.items())), (node.text or '').strip(), tuple(
        sorted(canonical(child) for child in node))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__ and DEVICE == ROM / 'device/xiaomi/sheng'
    audit = json.loads(args.audit.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert len(audit['repositories']) == 22 and audit['project_count'] == 1243
    assert all(r['passed'] and r['fetch']['returncode'] == 0 for r in audit['repositories'])
    work = args.work
    assert work.is_absolute() and work.parent.resolve(strict=True) == DIAG and not work.exists()
    work.mkdir()
    commands, inputs = [], {}

    def remember(path):
        path = path if path.is_absolute() else ROM / path
        assert path.is_file()
        inputs[str(path)] = sha(path)

    def run(command, environment=None):
        result = subprocess.run(list(map(str, command)), cwd=ROM, text=True, capture_output=True,
                                env=dict(os.environ, **(environment or {})))
        commands.append(dict(command=list(map(str, command)), returncode=result.returncode,
                             stdout=result.stdout, stderr=result.stderr, environment=environment))
        (work / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        assert result.returncode == 0, (command, result.stdout, result.stderr)

    policy = json.loads((DEVICE / 'docs/r32-policy-candidate-build-review-20261108.json').read_text())
    face = json.loads((DEVICE / 'docs/face-v2-candidate-build-20261108.json').read_text())
    assert policy['scoped_policy_build_passed'] and policy['existing_type_permission_delta_reviewed']
    assert policy['neverallow_checks_enabled'] and face['five_candidate_elf_checks_passed']
    for review in [policy, face]:
        for value in review['outputs'].values():
            assert sha(Path(value['path'])) == value['sha256']
    for name in ['r32-policy-candidate-build-review-20261108.json',
                 'face-v2-candidate-build-20261108.json', 'face-source-integration-review-20261108.json']:
        remember(DEVICE / 'docs' / name)
    original_files = json.loads((DEVICE / 'interfaces/biometrics/face/SOURCE_SHA256.json').read_text())
    face_root = DEVICE / 'interfaces/biometrics/face'
    assert len(original_files['original_sheng_firmware_files']) == 6
    for relative, value in original_files['original_sheng_firmware_files'].items():
        assert sha(face_root / relative) == value['sha256']
        remember(face_root / relative)

    matrix_sources = ['hardware/qcom-caf/common/vendor_framework_compatibility_matrix.xml',
                      'hardware/xiaomi/vintf/xiaomi_framework_compatibility_matrix.xml',
                      'device/xiaomi/sheng/configs/vintf/framework_dolby_matrix.xml']
    for path in matrix_sources:
        remember(Path(path))
    # Preserve the real product's normal assembly flags, including security
    # and AVB requirements. Omitting these would weaken the generated matrix.
    assert sha(PRODUCT / 'system' / MATRIX) == MATRIX_BASELINE
    original_matrix = ET.parse(PRODUCT / 'system' / MATRIX).getroot()
    versions = [v.text for v in original_matrix.findall('sepolicy/sepolicy-version')]
    version_file = PRODUCT / 'vendor/etc/selinux/plat_sepolicy_vers.txt'
    remember(version_file)
    current_version = version_file.read_text().strip()
    assert current_version in versions
    matrix_environment = dict(
        POLICYVERS=original_matrix.findtext('sepolicy/kernel-sepolicy-version'),
        PLATFORM_SEPOLICY_VERSION=current_version,
        PLATFORM_SEPOLICY_COMPAT_VERSIONS=' '.join(v for v in versions if v != current_version),
        FRAMEWORK_VBMETA_VERSION=original_matrix.findtext('avb/vbmeta-version'))
    assert all(matrix_environment.values())
    baseline_matrix = work / 'baseline-device-matrix.xml'
    run(['out/host/linux-x86/bin/assemble_vintf', '-i', ':'.join(matrix_sources), '-o', baseline_matrix], matrix_environment)
    assert sha(baseline_matrix) == sha(PRODUCT / 'system' / MATRIX) == MATRIX_BASELINE
    matrix_sources.append('device/xiaomi/sheng/configs/vintf/framework_face_matrix.xml')
    remember(Path(matrix_sources[-1]))
    matrix = work / 'candidate-device-matrix.xml'
    run(['out/host/linux-x86/bin/assemble_vintf', '-i', ':'.join(matrix_sources), '-o', matrix], matrix_environment)
    before, after = ET.parse(baseline_matrix).getroot(), ET.parse(matrix).getroot()
    added = [node for node in after if node.tag == 'hal' and node.findtext('name') == 'vendor.xiaomi.hardware.miface']
    assert len(added) == 1
    assert added[0].findtext('version') == '1.0'
    assert added[0].findtext('interface/name') == 'IMiFace'
    assert added[0].findtext('interface/instance') == 'default'
    after.remove(added[0])
    assert canonical(after) == canonical(before), 'Unrelated matrix content changed'

    # The baseline and the initial candidate check are retained separately.
    live = DIAG / 'r32-vintf-live-20261108'
    live_results = json.loads((live / 'results.json').read_text())
    assert live_results['commands'][0]['returncode'] == 0
    assert live_results['commands'][1]['returncode'] == 65
    assert 'vendor.xiaomi.hardware.miface@1.0::IMiFace/default' in live_results['commands'][1]['stderr']
    remember(live / 'results.json')
    vintf = work / 'vintf-candidate'
    shutil.copytree(live / 'candidate', vintf)
    shutil.copyfile(matrix, vintf / 'system' / MATRIX)
    command = ['out/host/linux-x86/bin/checkvintf', '--check-compat']
    for partition in ['system', 'system_ext', 'product', 'vendor', 'odm', 'apex']:
        command += ['--dirmap', '/' + partition + ':' + str(vintf / partition)]
    kernel = DIAG / 'r32-vintf-baseline-20261108/kernel.config'
    remember(kernel)
    command += ['--property', 'ro.product.first_api_level=34', '--property', 'ro.boot.product.hardware.sku=sheng',
                '--property', 'ro.boot.product.vendor.sku=kalama', '--property', 'apex.all.ready=true',
                '--kernel', '5.15.220:' + str(kernel)]
    run(command)

    payload = work / 'payload'

    def copy(source, partition, relative):
        remember(source)
        target = payload / partition / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    for name, value in face['outputs'].items():
        copy(Path(value['path']), 'vendor', 'lib64/' + name + '-V2-ndk.so')
    copy(Path(policy['outputs']['vendor_sepolicy.cil']['path']), 'vendor', 'etc/selinux/vendor_sepolicy.cil')
    copy(Path(policy['outputs']['precompiled_sepolicy']['path']), 'odm', 'etc/selinux/precompiled_sepolicy')
    for relative in original_files['original_sheng_firmware_files']:
        copy(face_root / relative, 'odm', relative)
    copy(ROM / 'frameworks/native/data/etc/android.hardware.biometrics.face.xml',
         'vendor', 'etc/permissions/android.hardware.biometrics.face.xml')
    copy(matrix, 'system', MATRIX)
    rules = [line for line in (DEVICE / 'sepolicy/vendor/file_contexts').read_text().splitlines()
             if line.endswith(('u:object_r:hal_face_default_exec:s0', 'u:object_r:hal_miface_default_exec:s0'))]
    assert len(rules) == 2
    additions = work / 'face-file-contexts'
    additions.write_text('\n'.join(rules) + '\n')
    remember(DEVICE / 'sepolicy/vendor/file_contexts')
    for original, output in [(PRODUCT / 'vendor/etc/selinux/vendor_file_contexts',
                              payload / 'vendor/etc/selinux/vendor_file_contexts'),
                             (GLOBAL_CONTEXTS, work / 'file_contexts.concat.tmp')]:
        remember(original)
        assert all(rule not in original.read_text() for rule in rules)
        run(['out/host/linux-x86/bin/fc_sort', '-i', original, additions, '-o', output])
        run(['out/host/linux-x86/bin/checkfc', Path(policy['outputs']['precompiled_sepolicy']['path']), output])
    hwservice = PRODUCT / 'vendor/etc/selinux/vendor_hwservice_contexts'
    remember(hwservice)
    entry = 'vendor.xiaomi.hardware.miface::IMiFace u:object_r:hal_miface_hwservice:s0'
    assert 'vendor.xiaomi.hardware.miface::IMiFace' not in hwservice.read_text()
    target = payload / 'vendor/etc/selinux/vendor_hwservice_contexts'
    target.write_bytes(hwservice.read_bytes().rstrip(b'\n') + b'\n' + entry.encode() + b'\n')
    run(['out/host/linux-x86/bin/checkfc', '-l', Path(policy['outputs']['precompiled_sepolicy']['path']), target])
    run(['out/host/linux-x86/bin/sefcontext_compile', '-p', Path(policy['outputs']['precompiled_sepolicy']['path']),
         '-o', work / 'file_contexts.bin', work / 'file_contexts.concat.tmp'])
    for path, digest in inputs.items():
        assert sha(Path(path)) == digest

    # Only after all gates pass, publish the explicit payload as build outputs.
    changes = {}
    for source in sorted(payload.rglob('*')):
        if not source.is_file():
            continue
        relative = source.relative_to(payload)
        destination = PRODUCT / relative
        previous = sha(destination) if destination.is_file() else None
        assert previous != sha(source), str(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        changes[str(relative)] = dict(before_sha256=previous, sha256=sha(source), bytes=source.stat().st_size)
    assert len(changes) == 14
    previous_contexts = sha(GLOBAL_CONTEXTS)
    shutil.copyfile(work / 'file_contexts.concat.tmp', GLOBAL_CONTEXTS)
    replaced_inputs = {path: inputs.pop(path) for path in list(inputs)
                       if Path(path) == GLOBAL_CONTEXTS or
                       (Path(path).is_relative_to(PRODUCT) and
                        str(Path(path).relative_to(PRODUCT)) in changes)}
    report = dict(revision=32, scoped_configuration_assembly_passed=True,
                  full_product_build_passed=False, normal_product_module_build_passed=False,
                  baseline_matrix_byte_reproduced=True, only_miface_matrix_hal_added=True,
                  complete_live_vintf_compatibility_passed=True, actual_kernel_config_checked=True,
                  kernel_release='5.15.220-gf9ca2b71f672',
                  exact_face_context_and_policy_checks_passed=True, payload_changes=changes,
                  global_contexts_before_sha256=previous_contexts, global_contexts_sha256=sha(GLOBAL_CONTEXTS),
                  inputs_sha256=inputs, replaced_build_inputs_before_sha256=replaced_inputs,
                  prebuild_audit_sha256=sha(args.audit),
                  builder_sha256=sha(Path(__file__)), commands_sha256=sha(work / 'commands.json'),
                  installed_on_device=False, device_operated=False, camera_opened=False)
    (work / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
