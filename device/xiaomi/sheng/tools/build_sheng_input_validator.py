#!/usr/bin/env python3
"""Finish only validatekeymaps' generated Rust archive and link, using exact Soong rules.

The full graph exceeds this host's available commit charge. All prerequisite
objects must already exist; this does not substitute flags or rebuild platform
sources with a custom configuration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROM = Path('/root/sheng-lineage/lineage-24.0')
MODULE = 'out/soong/.intermediates/frameworks/base/tools/validatekeymaps/validatekeymaps/linux_glibc_x86_64/'
TARGETS = {MODULE + 'generated_rust_staticlib/librustlibs.a', MODULE + 'validatekeymaps'}
HELPERS = {'linuxX8664LdFlagsDeps', 'rustToolchainImplicits'}


def blocks(path):
    pending = []
    with path.open() as stream:
        for line in stream:
            if line.strip() and not line[0].isspace():
                if pending:
                    yield ''.join(pending)
                pending = [line]
            else:
                pending.append(line)
        if pending:
            yield ''.join(pending)


def outputs(block):
    header = block.replace('$\n', '').split(':', 1)[0]
    return set(header.split()[1:]) if header.startswith('build ') else set()


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(data)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    top = ROM / 'out/soong/build.lineage_sheng.ninja'
    part = ROM / 'out/soong/build.lineage_sheng.9.ninja'
    globals_, rules, edges, helpers, helper_candidates = [], {}, {}, {}, {}
    for block in blocks(top):
        if block.startswith('g.') or block.startswith('m.validatekeymaps_linux_glibc_x86_64.'):
            globals_.append(block)
        elif block.startswith('rule '):
            rules[block.splitlines()[0].split()[1]] = block
        else:
            names = outputs(block)
            if len(names) == 1:
                name = next(iter(names))
                if '/' not in name:
                    assert name not in helper_candidates
                    helper_candidates[name] = block
    for block in blocks(part):
        selected = outputs(block) & TARGETS
        if selected:
            assert len(selected) == 1
            name = next(iter(selected))
            assert name not in edges
            edges[name] = block
    assert set(edges) == TARGETS
    # Toolchain aliases can also be introduced by global variable expansion.
    # Keep the original named phony statements; Ninja visits only dependencies
    # reachable from the two selected real build edges.
    for name, block in helper_candidates.items():
        header = block.replace('$\n', '').splitlines()[0].split(':', 1)[1].split()
        if header[0] == 'phony':
            helpers[name] = block
    assert HELPERS <= set(helpers)
    rule_names = {block.replace('$\n', '').split(':', 1)[1].split()[0]
                  for block in edges.values()}
    assert rule_names == {'g.cc.ld', 'g.rust.rustc'}, rule_names
    # The actual generated statements are copied verbatim. Missing dependencies
    # cause Ninja to fail; no synthetic phony rules hide missing build outputs.
    minimal = ('builddir = out\npool highmem_pool\n depth = 1\n\n'
               + '\n'.join(globals_)
               + '\n'.join(rules[name] for name in sorted(rule_names))
               + '\n'.join(helpers[name] for name in sorted(helpers))
               + '\n'.join(edges[name] for name in sorted(edges)))
    graph = work / 'validator.ninja'
    graph.write_text(minimal)
    ninja = ROM / 'prebuilts/build-tools/linux-x86/bin/ninja'
    target = MODULE + 'validatekeymaps'
    command = [str(ninja), '-f', str(graph), '-j1', target]
    commands = subprocess.check_output([str(ninja), '-f', str(graph), '-t', 'commands', target],
                                       cwd=ROM, text=True)
    (work / 'commands.txt').write_text(commands)
    subprocess.run(command, cwd=ROM, check=True)
    report = dict(host_validator_built=True, full_device_build_passed=False,
                  original_rule_and_edge_statements_unchanged=True,
                  original_named_dependency_helpers=sorted(helpers),
                  prerequisites_built_using_original_full_graph=True,
                  original_ninja_sha256={str(p.relative_to(ROM)): sha(p) for p in [top, part]},
                  command=command, output=str(ROM / target), output_sha256=sha(ROM / target),
                  generated_ninja_sha256=sha(graph), runtime_verified=False)
    (work / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
