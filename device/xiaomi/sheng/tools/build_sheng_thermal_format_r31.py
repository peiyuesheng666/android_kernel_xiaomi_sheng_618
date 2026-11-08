#!/usr/bin/env python3
"""Validate and assemble the exact r31 thermal-context and original-library delta."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
PRODUCT = ROM / 'out/target/product/sheng'
PROPERTY = 'vendor.sys.thermal.bcl.boot_completed'
ENTRY = PROPERTY + ' u:object_r:vendor_thermal_normal_prop:s0 exact bool'
LIBRARY_SHA = '7a1affdcba4a1dc835e5ac1944bbea864056fb38bec45c87538ef4df9a2be599'
CONTEXT_SHA = 'a56641111bb09bac804d983aaba98fbacd7322b69fce7163270d65e6b1ad8499'
POLICY_SHA = 'ccb422e37de241d4da50eb1ae8890cf1fe3fe895677658932b861d2de7e6471b'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__ and DEVICE == ROM / 'device/xiaomi/sheng'
    workspace = args.workspace.resolve(strict=True)
    audit_path = Path('/root/sheng-lineage/hardware-diagnostics/r31-prebuild-audit-20261108.json')
    audit = json.loads(audit_path.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert all(r['fetch']['returncode'] == 0 for r in audit['repositories'])
    work = workspace / 'artifacts/r31-config-assembly'
    work.mkdir(exist_ok=False)
    commands = []

    def run(command):
        command = list(map(str, command))
        result = subprocess.run(command, cwd=ROM, text=True, capture_output=True)
        commands.append(dict(command=command, returncode=result.returncode,
                             stdout=result.stdout, stderr=result.stderr))
        (work / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    source = DEVICE / 'sepolicy/vendor/property_contexts'
    assert source.read_text().splitlines().count(ENTRY) == 1
    assert 'set_prop(mi_thermald, vendor_thermal_normal_prop)' in (DEVICE / 'sepolicy/vendor/mi_thermald.te').read_text()
    original = PRODUCT / 'vendor/etc/selinux/vendor_property_contexts'
    assert sha(original) == CONTEXT_SHA
    policy = PRODUCT / 'odm/etc/selinux/precompiled_sepolicy'
    assert sha(policy) == POLICY_SHA
    shutil.copyfile(original, work / 'vendor-property-contexts.original')
    data = original.read_bytes()
    anchor = b'vendor.sys.thermal.data.path u:object_r:vendor_thermal_normal_prop:s0\n'
    assert data.count(anchor) == 1 and PROPERTY.encode() not in data
    candidate = work / 'vendor_property_contexts'
    candidate.write_bytes(data.replace(anchor, anchor + ENTRY.encode() + b'\n'))
    contexts = [PRODUCT / p / 'etc/selinux' / (p + '_property_contexts')
                for p in ('system_ext', 'product', 'odm')]
    contexts.insert(0, PRODUCT / 'system/etc/selinux/plat_property_contexts')
    assert all(p.is_file() for p in contexts)
    run([ROM / 'out/host/linux-x86/bin/property_info_checker', policy, *contexts, candidate])

    library = DEVICE / 'interfaces/compat/camera-format/libcamxexternalformatutils.so'
    assert library.stat().st_size == 36264 and sha(library) == LIBRARY_SHA
    clang = ROM / 'prebuilts/clang/host/linux-x86/clang-r596125/bin'
    symbols = run([clang / 'llvm-readelf', '--dyn-syms', library])
    loader = (DEVICE / 'interfaces/display/gralloc/gr_camera_info.cpp').read_text()
    required = set(re.findall(r'"(CamxFormatUtil_\w+)"', loader))
    assert len(required) == 16
    assert all(re.search(r'\b' + name + r'\s*$', symbols, re.M) for name in required)
    previous = Path('/root/sheng-lineage/hardware-diagnostics/graphicbuffer-abi-r25')
    old_commands = json.loads((previous / 'commands.json').read_text())
    old_inputs = shlex.split((previous / 'probe.rsp').read_text())
    needed = ('libcutils', 'liblog', 'libsync', 'libc++', 'libz', 'libc', 'libm', 'libdl')
    dependencies = {}
    for name in needed:
        matches = [ROM / p for p in old_inputs if Path(p).name == name + '.so']
        if not matches:
            installed = PRODUCT / 'vendor/lib64' / (name + '.so')
            matches = [installed] if installed.is_file() else list(
                (ROM / 'out/soong/.intermediates/system/core' / name / name).glob('android_vendor_arm64*_shared/' + name + '.so'))
        assert len(matches) == 1 and matches[0].is_file(), (name, matches)
        dependencies[name] = matches[0]
    command = [sys.executable, ROM / 'build/make/tools/check_elf_file.py',
               '--llvm-readobj', clang / 'llvm-readobj', '--soname', library.name]
    for path in dependencies.values(): command.extend(['--shared-lib', path])
    run([*command, library])

    # Reuse recorded successful compiler/linker arguments without loading the full Ninja graph.
    compile_command, link_command = [[part.replace(str(previous), str(work)) for part in c]
                                     for c in old_commands]
    compile_command[-1] = str(DEVICE / 'tools/ShengCameraFormatProbe.cpp')
    inputs = [part.replace(str(previous), str(work)) for part in old_inputs]
    (work / 'probe.rsp').write_text(shlex.join(inputs) + '\n')
    link_command[link_command.index('-o') + 1] = str(work / 'sheng-camera-format-probe')
    run(compile_command)
    run(link_command)
    destination = PRODUCT / 'vendor/lib64' / library.name
    assert not destination.exists() and not destination.is_symlink()
    shutil.copyfile(library, destination)
    shutil.copyfile(candidate, original)
    sources = ['device.mk', 'sepolicy/vendor/property_contexts', 'sepolicy/vendor/mi_thermald.te',
               'interfaces/compat/camera-format/Android.bp', 'interfaces/compat/camera-format/' + library.name,
               'tools/ShengCameraFormatProbe.cpp', 'tools/build_sheng_thermal_format_r31.py']
    review = dict(revision=31, scoped_configuration_assembly_passed=True,
        full_product_build_passed=False, property_info_checker_passed=True,
        original_library_elf_check_passed=True, required_camx_exports=sorted(required),
        diagnostic_native_build_passed=True, systemui_changed=False,
        prebuild_audit_sha256=sha(audit_path), command_log_sha256=sha(work / 'commands.json'),
        original_context_sha256=CONTEXT_SHA, unchanged_policy_sha256=POLICY_SHA,
        source_sha256={p: sha(DEVICE / p) for p in sources},
        dependencies_sha256={str(p.relative_to(ROM)): sha(p) for p in dependencies.values()},
        reviewed_sha256={'vendor': {'etc/selinux/vendor_property_contexts': sha(original),
                                    'lib64/' + library.name: sha(destination)}},
        native_probe_sha256=sha(work / 'sheng-camera-format-probe'),
        installed=False, runtime_verified=False)
    path = DEVICE / 'docs/r31-thermal-format-build-review-20261108.json'
    assert not path.exists()
    path.write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps(review, indent=2))


if __name__ == '__main__':
    main()
