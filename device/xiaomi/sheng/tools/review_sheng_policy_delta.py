#!/usr/bin/env python3
"""Compare existing-type permissions through the current ROM's binary parser.

Do not discard extended ioctl/netlink rules or expand the complete rule graph
into individual permission objects. This is host-only review evidence.
"""
import argparse
from collections import defaultdict
import functools
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROM = Path('/root/sheng-lineage/lineage-24.0')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse(line):
    stack, root = [], None
    for token in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', line):
        if token == '(':
            node = []
            if stack:
                stack[-1].append(node)
            else:
                assert root is None
                root = node
            stack.append(node)
        elif token == ')':
            assert stack
            stack.pop()
        else:
            assert stack
            stack[-1].append(token)
    assert root and not stack
    return root


def frozen(value):
    return tuple(map(frozen, value)) if isinstance(value, list) else value


class Policy:
    def __init__(self, path):
        self.forms = [parse(line) for line in path.read_text().splitlines() if line.strip()]
        self.types = {form[1] for form in self.forms if form[0] == 'type'}
        self.attributes = {form[1]: form[2] for form in self.forms
                           if form[0] == 'typeattributeset'}
        assert all(isinstance(members, list) and all(isinstance(v, str) for v in members)
                   for members in self.attributes.values())
        assert not any(form[0] in ('boolean', 'booleanif', 'tunableif') for form in self.forms)

    @functools.lru_cache(maxsize=None)
    def members(self, name):
        if name in self.types:
            return frozenset([name])
        assert name in self.attributes, name
        return frozenset().union(*(self.members(v) for v in self.attributes[name]))

    def prepare(self, common, bits):
        self.common = common
        self.bits = bits
        self.index = defaultdict(list)
        for form in self.forms:
            if form[0] not in ('allow', 'auditallow', 'dontaudit'):
                continue
            source, target, (tclass, permissions) = form[1:]
            sources = self.members(source) & common
            mask = None if target == 'self' else self.mask(target)
            for name in sources:
                self.index[name].append((form[0], tclass, permissions, mask))

    @functools.lru_cache(maxsize=None)
    def mask(self, name):
        return sum(self.bits[v] for v in self.members(name) & self.common)

    def rows(self, name):
        rows = defaultdict(int)
        for kind, tclass, permissions, target in self.index[name]:
            if target is None:
                target = self.bits[name]
            for permission in permissions:
                rows[kind, tclass, permission] |= target
        return rows

    def non_av_rules(self):
        values = set()
        for form in self.forms:
            kind = form[0]
            if kind not in ('allowx', 'auditallowx', 'dontauditx',
                            'typetransition', 'typechange', 'typemember'):
                continue
            source, target = form[1:3]
            sources = tuple(sorted(self.members(source) & self.common))
            targets = 'self' if target == 'self' else tuple(sorted(self.members(target) & self.common))
            if not sources or not targets:
                continue
            if kind in ('typetransition', 'typechange', 'typemember'):
                # The default type is last, after an optional filename.
                if form[-1] not in self.common:
                    continue
            values.add((kind, sources, targets, frozen(form[3:])))
        return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__ and args.work.parent.resolve(strict=True) == Path('/root/sheng-lineage/hardware-diagnostics')
    assert not args.work.exists()
    args.work.mkdir()
    executable = ROM / 'out/host/linux-x86/bin/checkpolicy'
    records, policies = [], []
    hashes = {str(p): sha(p) for p in [args.baseline, args.candidate, executable]}
    for label, path in [('baseline', args.baseline), ('candidate', args.candidate)]:
        output = args.work / (label + '.cil')
        command = [str(executable), '-b', '-M', '-C', '-o', str(output), str(path)]
        result = subprocess.run(command, capture_output=True, text=True)
        records.append(dict(command=command, returncode=result.returncode,
                            stdout=result.stdout, stderr=result.stderr))
        (args.work / 'commands.json').write_text(json.dumps(records, indent=2) + '\n')
        assert result.returncode == 0, result.stderr
        hashes[str(output)] = sha(output)
        policies.append(Policy(output))
    left, right = policies
    common = left.types & right.types
    names = sorted(common)
    bits = {name: 1 << i for i, name in enumerate(names)}
    for policy in policies:
        policy.prepare(common, bits)
    added, removed = [], []

    def emit(destination, source, key, mask):
        while mask:
            low = mask & -mask
            target = names[low.bit_length() - 1]
            destination.append(dict(kind=key[0], source=source, target=target,
                                    tclass=key[1], permission=key[2]))
            mask ^= low

    for name in names:
        before, after = left.rows(name), right.rows(name)
        for key in before.keys() | after.keys():
            emit(added, name, key, after.get(key, 0) & ~before.get(key, 0))
            emit(removed, name, key, before.get(key, 0) & ~after.get(key, 0))
    non_av_before, non_av_after = left.non_av_rules(), right.non_av_rules()
    ignored = {'type', 'typeattribute', 'typeattributeset', 'roletype', 'allow', 'auditallow',
               'dontaudit', 'allowx', 'auditallowx', 'dontauditx', 'typetransition', 'typechange', 'typemember'}
    other_before = {frozen(v) for v in left.forms if v[0] not in ignored}
    other_after = {frozen(v) for v in right.forms if v[0] not in ignored}
    roles_before = {frozen(v) for v in left.forms if v[0] == 'roletype' and v[2] in common}
    roles_after = {frozen(v) for v in right.forms if v[0] == 'roletype' and v[2] in common}
    membership = {}
    for attr in left.attributes.keys() & right.attributes.keys():
        if attr.startswith('base_typeattr_'):
            continue
        before, after = left.members(attr) & common, right.members(attr) & common
        if before != after:
            membership[attr] = dict(added=sorted(after - before), removed=sorted(before - after))
    for path, digest in hashes.items():
        assert sha(Path(path)) == digest
    report = dict(binary_parser='current ROM checkpolicy -b -M -C; no xperm formats skipped',
                  inputs_and_decompiled_sha256=hashes, builder_sha256=sha(Path(__file__)),
                  compared_existing_types=len(common), added_types=sorted(right.types - left.types),
                  removed_types=sorted(left.types - right.types),
                  added_existing_type_permissions=sorted(added, key=lambda v: tuple(v.values())),
                  removed_existing_type_permissions=sorted(removed, key=lambda v: tuple(v.values())),
                  existing_type_attribute_membership_changes=membership,
                  existing_type_non_av_rule_forms_added=sorted(non_av_after - non_av_before),
                  existing_type_non_av_rule_forms_removed=sorted(non_av_before - non_av_after),
                  existing_role_type_statements_added=sorted(roles_after - roles_before),
                  existing_role_type_statements_removed=sorted(roles_before - roles_after),
                  other_statements_added=sorted(other_after - other_before),
                  other_statements_removed=sorted(other_before - other_after),
                  baseline_permissive_domains=sorted(v[1] for v in left.forms if v[0] == 'typepermissive'),
                  candidate_permissive_domains=sorted(v[1] for v in right.forms if v[0] == 'typepermissive'),
                  installed=False, camera_opened=False,
                  scope='Exact ordinary AV permissions between existing types; normalized extended and transition rule forms; new-type permissions still require separate review.')
    output = args.work / 'policy-delta.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ['inputs_and_decompiled_sha256']}, indent=2))


if __name__ == '__main__':
    main()
