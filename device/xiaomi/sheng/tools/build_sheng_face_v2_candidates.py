#!/usr/bin/env python3
"""Build frozen public V2 face interfaces as isolated, uninstalled candidates.

Read existing Soong command text without loading or executing the complete graph.
Do not change public sources, installed product trees, service state or devices.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
COMMON = 'android.hardware.biometrics.common'
FACE = 'android.hardware.biometrics.face'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def logical_lines(path):
    value = ''
    with path.open() as stream:
        for line in stream:
            line = line.rstrip('\n')
            continuation = line.endswith('$')
            value += line[:-1] if continuation else line
            if not continuation:
                yield value
                value = ''
    assert not value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__ and DEVICE == ROM / 'device/xiaomi/sheng'
    audit = json.loads(args.audit.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert len(audit['repositories']) == 22
    assert all(r['passed'] and r['fetch']['returncode'] == 0 for r in audit['repositories'])
    assert any(r['path'] == 'hardware/interfaces' for r in audit['repositories'])
    work = args.work
    assert work.is_absolute() and not work.exists()
    assert work.parent.resolve(strict=True) == Path('/root/sheng-lineage/hardware-diagnostics')
    work.mkdir()
    commands = []

    def run(command):
        command = list(map(str, command))
        result = subprocess.run(command, cwd=ROM, text=True, capture_output=True)
        commands.append(dict(command=command, returncode=result.returncode,
                             stdout=result.stdout, stderr=result.stderr))
        (work / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    # The current emitted vendor command templates are inputs, not a build graph
    # to be executed. Freeze their exact source bytes in the result.
    root = ROM / 'out/soong/build.lineage_sheng.ninja'
    shard = ROM / 'out/soong/build.lineage_sheng.2.ninja'
    variables, templates = {}, {}
    assignment = re.compile(r'^([A-Za-z0-9_.-]+) = (.*)$')
    for line in logical_lines(root):
        match = assignment.match(line)
        if match and match[1].startswith('g.'):
            variables[match[1]] = match[2]
    current = None
    for line in logical_lines(shard):
        match = assignment.match(line)
        if match and (match[1].startswith('g.') or any(p in match[1] for p in (COMMON, FACE))):
            variables[match[1]] = match[2]
        if line.startswith('build '):
            current = None
            output = line.split(':', 1)[0]
            for module, version in [(COMMON, 4), (FACE, 5)]:
                if (f'/{module}-V{version}-ndk/android_vendor_arm64_' in output
                        and output.endswith(f'/unstripped/{module}-V{version}-ndk.so')):
                    assert module not in templates
                    current = templates[module] = {}
        elif current is not None:
            match = re.match(r'^    (\w+) = ?(.*)$', line)
            if match:
                current[match[1]] = match[2]
            elif not line:
                current = None
    assert set(templates) == {COMMON, FACE}

    def expand(value):
        pattern = re.compile(r'\$\{([^}]+)\}|\$([A-Za-z0-9_.-]+)')
        for _ in range(40):
            if '$' not in value:
                return value
            before = value
            value = pattern.sub(lambda m: variables[m[1] or m[2]], value)
            assert value != before, value
        raise AssertionError('Recursive/unresolved Ninja variable')

    roots = {
        COMMON: ROM / 'hardware/interfaces/biometrics/common/aidl/aidl_api' / COMMON / '2',
        FACE: ROM / 'hardware/interfaces/biometrics/face/aidl/aidl_api' / FACE / '2',
    }
    imports = [*roots.values(),
        ROM / 'hardware/interfaces/common/aidl/aidl_api/android.hardware.common/2',
        ROM / 'hardware/interfaces/keymaster/aidl/aidl_api/android.hardware.keymaster/3']
    assert all(p.is_dir() for p in imports)
    sources = {}
    for directory in imports:
        for path in directory.rglob('*'):
            if path.is_file():
                sources[str(path.relative_to(ROM))] = sha(path)
    outputs = {}
    for module, old_version in [(COMMON, 4), (FACE, 5)]:
        stage = work / module
        stage.mkdir()
        generated = stage / 'gen'
        headers = generated / 'include'
        generated.mkdir()
        headers.mkdir()
        interface_hash = (roots[module] / '.hash').read_text().splitlines()[-1]
        assert re.fullmatch(r'[0-9a-f]{40}', interface_hash)
        aidl = [ROM / 'out/host/linux-x86/bin/aidl', '--lang=ndk', '--structured',
                '--stability=vintf', '--min_sdk_version=37', '--version=2',
                '--hash=' + interface_hash, '-o', generated, '-h', headers]
        for directory in imports:
            aidl += ['-I', directory]
        aidl += sorted(roots[module].rglob('*.aidl'))
        run(aidl)
        prefix = (f'm.{module}-V{old_version}-ndk_android_vendor_arm64_'
                  'armv8-2a-dotprod_kryo_static.cFlags1')
        flags = expand(variables[prefix])
        for name, version in [(COMMON, 4), (FACE, 5)]:
            package = 'common' if name == COMMON else 'face'
            original = (f'out/soong/.intermediates/hardware/interfaces/biometrics/{package}/aidl/'
                        f'{name}-V{version}-ndk-source/gen/include')
            flags = flags.replace(original, str(work / name / 'gen/include'))
        flags = flags.replace('android.hardware.keymaster-V4-ndk-source',
                              'android.hardware.keymaster-V3-ndk-source')
        objects = []
        for source in sorted(generated.rglob('*.cpp')):
            output = stage / (source.stem + '.o')
            assert output not in objects
            run([ROM / 'prebuilts/clang/host/linux-x86/clang-r596125/bin/clang++',
                 *shlex.split(flags), '-c', source, '-o', output])
            objects.append(output)
        assert objects
        template = templates[module]
        linker_flags = expand(template['ldFlags']).replace(
            f'{module}-V{old_version}-ndk.so', f'{module}-V2-ndk.so')
        libraries = shlex.split(expand(template['libFlags']))
        for i, name in enumerate(libraries):
            if f'{COMMON}-V4-ndk.so' in name:
                libraries[i] = str(outputs[COMMON])
            elif 'android.hardware.keymaster-V4-ndk' in name:
                libraries[i] = name.replace('android.hardware.keymaster-V4-ndk',
                                             'android.hardware.keymaster-V3-ndk')
        assert all((ROM / p).is_file() for p in libraries), libraries
        output = stage / (module + '-V2-ndk.so')
        run([*shlex.split(expand(template['ldCmd'])), *shlex.split(linker_flags),
             '-o', output, *shlex.split(template['crtBegin']), *objects,
             *libraries, *shlex.split(template['crtEnd'])])
        outputs[module] = output
        print('Built isolated frozen V2 candidate: ' + output.name, flush=True)
    result = dict(candidate_interfaces_built=True, full_product_build_passed=False,
        installed=False, device_operated=False, camera_opened=False,
        audit_sha256=sha(args.audit), builder_sha256=sha(Path(__file__)),
        input_source_sha256=sources,
        command_templates_sha256={str(p.relative_to(ROM)): sha(p) for p in [root, shard]},
        outputs={name: dict(path=str(p), sha256=sha(p), bytes=p.stat().st_size)
                 for name, p in outputs.items()}, command_log_sha256=sha(work / 'commands.json'))
    (work / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
