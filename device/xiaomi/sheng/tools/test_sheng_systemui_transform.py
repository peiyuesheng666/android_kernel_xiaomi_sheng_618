#!/usr/bin/env python3
"""Review real SystemUI output and fail-closed behavior using malformed APK fixtures."""
import argparse
import os
from pathlib import Path
import subprocess
import zipfile

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    jdk = ROM / 'prebuilts/jdk/jdk21/linux-x86/bin'
    java_env = dict(os.environ, JAVA_HOME=str(jdk.parent), PATH=str(jdk) + ':' + os.environ['PATH'])
    jar = ROM / ('out/soong/.intermediates/device/xiaomi/sheng/interfaces/compat/systemui/'
                 'sheng-systemui-power-patcher/linux_glibc_common/combined/sheng-systemui-power-patcher.jar')
    assert jar.is_file()
    patcher = [jdk / 'java', '-Xmx2g', '-cp', jar, 'ShengSystemUiPowerPatcher']
    subprocess.run([jdk / 'javac', '-cp', jar, '-d', args.work,
                    DEVICE / 'interfaces/compat/systemui/tests/ShengSystemUiApkVerifier.java'], check=True)
    subprocess.run([jdk / 'java', '-Xmx2g', '-cp', f'{args.work}:{jar}',
                    'ShengSystemUiApkVerifier', args.original, args.output], check=True)
    with zipfile.ZipFile(args.original) as apk:
        entries = {info.filename: apk.read(info) for info in apk.infolist()}
    dexes = [name for name in entries if name.endswith('.dex')]
    assert dexes
    target = [name for name in dexes if b'getPowerButtonOrigin\0' in entries[name]]
    assert len(target) == 1

    def rejection(name, changes, helper=args.helper, message=''):
        source = args.work / (name + '.apk')
        with zipfile.ZipFile(source, 'w') as apk:
            for key, value in changes.items():
                apk.writestr(key, value)
        result = subprocess.run([*patcher, source, helper, args.work / (name + '-out.apk')],
                                capture_output=True, text=True, timeout=90, env=java_env)
        (args.work / (name + '.log')).write_text(result.stdout + result.stderr)
        assert result.returncode != 0, f'Malformed input accepted: {name}'
        assert message in result.stdout + result.stderr, (name, result.stderr)
        print(f'PASS rejected {name}', flush=True)

    rejection('missing-target-dex', {k: v for k, v in entries.items() if k != target[0]},
              message='Expected exactly one definition')
    duplicate = dict(entries)
    duplicate[f'classes{len(dexes)+1}.dex'] = entries[dexes[0]]
    rejection('duplicate-classes', duplicate, message='Duplicate class')
    gap = dict(entries)
    highest = max(dexes, key=lambda name: 1 if name == 'classes.dex' else int(name[7:-4]))
    gap[f'classes{len(dexes)+2}.dex'] = gap.pop(highest)
    rejection('noncontiguous-dex', gap, message='Noncontiguous multidex layout')
    renamed = dict(entries)
    renamed[target[0]] = renamed[target[0]].replace(b'getPowerButtonOrigin\0', b'getPowerButtonOrigiX\0')
    rejection('renamed-target-method', renamed, message='Expected exactly one definition')
    rejection('wrong-helper', entries, helper=args.original, message='Unexpected helper')
    with zipfile.ZipFile(args.output) as apk:
        transformed = {info.filename: apk.read(info) for info in apk.infolist()}
    rejection('already-transformed', transformed, message='Helper already present')
    print('Real APK semantic review and six malformed-input checks passed.', flush=True)


if __name__ == '__main__':
    main()
