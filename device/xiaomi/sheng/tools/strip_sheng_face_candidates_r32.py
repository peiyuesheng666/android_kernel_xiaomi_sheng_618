#!/usr/bin/env python3
"""Apply normal Soong stripping to the two reviewed, unstripped V2 candidates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess

from build_sheng_face_v2_candidates import logical_lines

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
DIAG = Path('/root/sheng-lineage/hardware-diagnostics')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_elf(path):
    data = path.read_bytes()
    assert data[:6] == b'\x7fELF\x02\x01'
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    assert header[2] == 183 and header[11] == 64
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, header[6] + i * 64)
                for i in range(header[12])]
    names_section = sections[header[13]]
    names = data[names_section[4]:names_section[4] + names_section[5]]
    allocated = {}
    for section in sections:
        if not section[2] & 2:
            continue
        name = names[section[0]:].split(b'\0', 1)[0].decode()
        payload = data[section[4]:section[4] + section[5]] if section[1] != 8 else b''
        allocated[name] = (section[1:6], hashlib.sha256(payload).hexdigest())
    programs = data[header[5]:header[5] + header[9] * header[10]]
    return header[1:6], programs, allocated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__ and DEVICE == ROM / 'device/xiaomi/sheng'
    audit = json.loads(args.audit.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert len(audit['repositories']) == 22
    assert all(r['passed'] and r['fetch']['returncode'] == 0 for r in audit['repositories'])
    assert args.work.is_absolute() and args.work.parent.resolve(strict=True) == DIAG and not args.work.exists()
    args.work.mkdir()
    root, shard = (ROM / 'out/soong' / name for name in ('build.lineage_sheng.ninja', 'build.lineage_sheng.2.ninja'))
    variables, rule = {}, None
    assignment = re.compile(r'^([A-Za-z0-9_.-]+) = (.*)$')
    lines = iter(logical_lines(root))
    for line in lines:
        match = assignment.match(line)
        if match and match[1].startswith('g.'):
            variables[match[1]] = match[2]
        if line == 'rule g.cc.strip':
            rule = next(lines).strip()
    assert rule == ('command = XZ=${g.cc.xzCmd} CREATE_MINIDEBUGINFO=${g.cc.createMiniDebugInfo} '
                    'CLANG_BIN=${g.android.soong.cc.config.ClangBin} ${g.cc.stripPath} '
                    '${args} -i ${in} -o ${out} -d ${out}.d')
    selected, current = {}, None
    for line in logical_lines(shard):
        if line.startswith('build '):
            current = None
            output, dependencies = line.split(':', 1)
            for module, version in [('common', 4), ('face', 5)]:
                if (f'/android.hardware.biometrics.{module}-V{version}-ndk/android_vendor_arm64_' in output
                        and output.endswith('.so') and dependencies.split()[0] == 'g.cc.strip'):
                    assert module not in selected
                    current = selected[module] = dict(build=line, args='')
        elif current is not None and line.startswith('    args ='):
            current['args'] = line.split('=', 1)[1].strip()
    assert set(selected) == {'common', 'face'}
    assert all(v['args'].replace('$ ', ' ').strip() == '--keep-mini-debug-info' for v in selected.values())

    def expand(value):
        for _ in range(30):
            if '$' not in value:
                return value
            value = re.sub(r'\$\{([^}]+)\}', lambda m: variables[m[1]], value)
        raise AssertionError('Unresolved normal strip variable')

    environment = dict(os.environ, **{key: str(ROM / expand('${' + variable + '}'))
        for key, variable in [('XZ', 'g.cc.xzCmd'), ('CREATE_MINIDEBUGINFO', 'g.cc.createMiniDebugInfo'),
                              ('CLANG_BIN', 'g.android.soong.cc.config.ClangBin')]})
    strip = ROM / expand('${g.cc.stripPath}')
    source_report = json.loads((DEVICE / 'docs/face-v2-candidate-build-20261108.json').read_text())
    original_checks = DIAG / 'face-v2-candidates-20261108/rebuilt-interface-complete-elf-checks.json'
    replacements, outputs, commands = {}, {}, []
    for module in ('common', 'face'):
        name = 'android.hardware.biometrics.' + module
        source = Path(source_report['outputs'][name]['path'])
        assert sha(source) == source_report['outputs'][name]['sha256']
        target = args.work / source.name
        command = [str(strip), '--keep-mini-debug-info', '-i', str(source), '-o', str(target), '-d', str(target) + '.d']
        result = subprocess.run(command, cwd=ROM, env=environment, text=True, capture_output=True)
        commands.append(dict(command=command, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
        assert result.returncode == 0, result.stderr
        assert runtime_elf(source) == runtime_elf(target), 'Runtime ELF sections/program headers changed'
        assert target.stat().st_size < source.stat().st_size
        replacements[str(source)] = str(target)
        outputs[name] = dict(path=str(target), sha256=sha(target), bytes=target.stat().st_size,
                             unstripped_sha256=sha(source), allocated_sections_and_program_headers_preserved=True)
    checks = json.loads(original_checks.read_text())
    assert len(checks) == 5 and all(c['returncode'] == 0 for c in checks)
    for check in checks:
        assert sha(Path(check['binary'])) == check['sha256']
        for provider in check['providers'].values():
            assert sha(Path(provider['path'])) == provider['sha256']
        command = [replacements.get(part, part) for part in check['command']]
        result = subprocess.run(command, cwd=ROM, text=True, capture_output=True)
        commands.append(dict(command=command, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
        assert result.returncode == 0, result.stderr
    (args.work / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    # Product mutation happens only after both transformations and all five ELF checks pass.
    for output in outputs.values():
        source = Path(output['path'])
        installed = ROM / 'out/target/product/sheng/vendor/lib64' / source.name
        assert sha(installed) == output['unstripped_sha256']
    for output in outputs.values():
        source = Path(output['path'])
        shutil.copyfile(source, ROM / 'out/target/product/sheng/vendor/lib64' / source.name)
    report = dict(normal_strip_rule_reused=True, normal_strip_args='--keep-mini-debug-info',
        all_runtime_elf_sections_preserved=True, five_candidate_elf_checks_passed=True,
        full_product_build_passed=False, normal_product_module_build_passed=False,
        outputs=outputs, strip_edges=selected, strip_environment={k: environment[k] for k in
            ('XZ', 'CREATE_MINIDEBUGINFO', 'CLANG_BIN')},
        inputs_sha256={str(p): sha(p) for p in [root, shard, strip, Path(environment['CLANG_BIN']) / 'llvm-strip',
                                               original_checks, args.audit, Path(__file__)]},
        commands_sha256=sha(args.work / 'commands.json'), installed_on_device=False, camera_opened=False)
    (args.work / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
