#!/usr/bin/env python3
"""Rebuild unchanged SystemUI module edges from the existing generated Soong graph.

This is an incremental module build, not a complete product build. No public
sources, compiler flags, dependency declarations or signing rules are replaced.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from build_sheng_input_validator import blocks, outputs

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = ROM / 'device/xiaomi/sheng'
PREFIX = 'out/soong/.intermediates/device/xiaomi/sheng/interfaces/compat/systemui/'
PATCHER = PREFIX + 'sheng-systemui-power-patcher/linux_glibc_common/'
APK = PREFIX + 'ShengSystemUI/android_common/'
TARGETS = {
    PATCHER + 'javac/sheng-systemui-power-patcher.jar',
    PATCHER + 'combined/sheng-systemui-power-patcher.jar',
    PREFIX + 'sheng-systemui-power-apk/android_common/gen/ShengSystemUI-unsigned.apk',
    APK + 'jnis-uncompressed/ShengSystemUI.apk',
    APK + 'dex-uncompressed/ShengSystemUI.apk',
    APK + 'signed/SystemUI.apk',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    # This build reuses the generated graph only while the declarations match
    # the formally reviewed r24 build. Java body edits do not alter that graph.
    baseline = json.loads((DEVICE / 'docs/build-r24-video-power-20261108.json').read_text())
    bp = 'interfaces/compat/systemui/Android.bp'
    assert sha(DEVICE / bp) == baseline['source_sha256'][bp]
    top = ROM / 'out/soong/build.lineage_sheng.ninja'
    shard = ROM / 'out/soong/build.lineage_sheng.0.ninja'
    variables, rules, helpers, edges = [], {}, {}, {}
    for path in (top, shard):
        for block in blocks(path):
            if block.startswith('g.') or any(block.startswith('m.11-' + module) for module in (
                    'ShengSystemUI_', 'sheng-systemui-power-patcher_', 'sheng-systemui-power-apk_')):
                variables.append(block)
            elif block.startswith('rule '):
                rules[block.splitlines()[0].split()[1]] = block
            elif block.startswith('build '):
                names = outputs(block)
                selected = names & TARGETS
                if selected:
                    assert len(selected) == 1
                    name = next(iter(selected))
                    assert name not in edges
                    edges[name] = block
                elif len(names) == 1:
                    name = next(iter(names))
                    rule = block.replace('$\n', '').split(':', 1)[1].split()[0]
                    if '/' not in name and rule == 'phony':
                        assert name not in helpers or helpers[name] == block
                        helpers[name] = block
    assert set(edges) == TARGETS
    # Host-tool aliases can be defined in shards belonging to their providers.
    # Keep their real declarations instead of inventing empty prerequisites.
    for path in sorted((ROM / 'out/soong').glob('build.lineage_sheng.[0-9]*.ninja')):
        if path == shard:
            continue
        for block in blocks(path):
            if not block.startswith('build '):
                continue
            names = outputs(block)
            if len(names) != 1:
                continue
            name = next(iter(names))
            if '/' not in name and block.replace('$\n', '').split(':', 1)[1].split()[0] == 'phony':
                assert name not in helpers or helpers[name] == block
                helpers[name] = block
    selected_rules = {b.replace('$\n', '').split(':', 1)[1].split()[0] for b in edges.values()}
    assert selected_rules == {'g.java.javac', 'g.java.combineJar',
                              'm.11-sheng-systemui-power-apk_android_common.generator',
                              'g.java.uncompress-embedded-jni-libs', 'g.java.uncompress-dex', 'g.java.signapk'}
    ninja = work / 'systemui.ninja'
    ninja.write_text('builddir = out\npool highmem_pool\n depth = 1\n\n'
                     + '\n'.join(variables) + '\n'
                     + '\n'.join(rules[name] for name in sorted(selected_rules)) + '\n'
                     + '\n'.join(helpers.values()) + '\n'
                     + '\n'.join(edges.values()))
    # Keep failed signed output available for regression tests and diagnosis.
    signed = ROM / (APK + 'signed/SystemUI.apk')
    shutil.copyfile(signed, work / 'previous-signed-SystemUI.apk')
    command = [str(ROM / 'prebuilts/build-tools/linux-x86/bin/ninja'), '-f', str(ninja),
               '-j1', APK + 'signed/SystemUI.apk']
    env = dict(os.environ)
    jdk = str(ROM / 'prebuilts/jdk/jdk21/linux-x86')
    env.update(JAVA_HOME=jdk, PATH=jdk + '/bin:' + env['PATH'])
    (work / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    result = subprocess.run(command, cwd=ROM, env=env, capture_output=True, text=True)
    (work / 'build.log').write_text(result.stdout + result.stderr)
    print(result.stdout + result.stderr, flush=True)
    receipt = dict(module_build_passed=result.returncode == 0, full_product_build=False,
                   rules_copied_verbatim=True, fabricated_dependencies=False,
                   generated_graph_sha256={str(p): sha(p) for p in (top, shard)},
                   subset_sha256=sha(ninja), source_sha256={str(p.relative_to(DEVICE)): sha(p)
                   for p in [DEVICE / bp, DEVICE / 'interfaces/compat/systemui/host/ShengSystemUiPowerPatcher.java']},
                   signed_apk_sha256=sha(signed) if result.returncode == 0 else None,
                   runtime_verified=False)
    (work / 'build-result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    assert result.returncode == 0


if __name__ == '__main__':
    main()
