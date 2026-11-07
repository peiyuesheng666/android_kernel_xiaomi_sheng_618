#!/usr/bin/env python3
"""Package r21 Settings identity, panel DPI and tablet compatibility over r20."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import stat
import struct
import subprocess
import sys

from freeze_sheng_batch_inputs import CompiledContexts, erofs_new_nodes
from package_sheng_batch_helpers import (
    certificates, debugfs, erofs_input_keys, ext4_snapshot, inode_number,
    merge_parent, new_metadata, packaging_input_path, publish_batch,
    relative_path, stage_erofs, stage_ext4, tree_descriptor, validate_inputs,
    validate_packaging_inputs,
)
from package_sheng_color_functions import source_paths
from package_sheng_model_followup import HOST, PRODUCT, ROM, parse_image, sha

DEVICE = Path(__file__).resolve().parents[1]
PINNED = {
    'odm': ('r19', 1141067776, '405d4004558bf5caea30874f301780d2a180c2da0ecc1ba143f7bdaa3ac1dfcf'),
    'vendor': ('r19', 303517696, '140df691149b4b731caf2dca730de4403b6cf45bb1e7a004a1dbc228b1d4c8b5'),
    'vbmeta': ('r19', 8192, 'd31c33d7a479cb621e7b25e97afaf5636de3eea64e0c75a294420f313ffe9ba5'),
    'system': ('r20', 1005133824, '0f9c8ad6341faae4abaa9c080614d6d879aa62e85e36383086bb0333adfb4dce'),
    'vbmeta_system': ('r20', 4096, 'bb396433319e6d1f77cb24f6f223b08de107d6e266838bc156c81acf526374e8'),
    'system_ext': ('r19', 572813312, '9663016b59a90b30cb573dd45785f01ef1ef0ccefad6572279051cdec92a220a'),
}
SCOPE = {
    'odm': {'overlay/SettingsResOverlaySheng.apk'},
    'vendor': {'lib64/libsdmdal.so'},
    'system_ext': {'framework/sheng-tablet-compat.jar',
                   'etc/init/sheng-tablet-compat.rc', 'etc/sheng/bootclasspath.pb'},
}
BUILD = json.loads((DEVICE / 'docs/build-r21-settings-identity-20261107.json').read_text())
assert BUILD['build_passed'] and BUILD['resource_link_probe_passed'] and BUILD['classpath_schema_test_passed']
REVIEWED_SHA256 = BUILD['reviewed_sha256']
OUTPUTS = {p: PINNED[p][1] for p in (*SCOPE, 'vbmeta', 'vbmeta_system')}
NODES = SCOPE['system_ext'] | {'etc/sheng'}
EXPECTED_NODES = {'odm': set(), 'vendor': set(), 'system_ext': NODES}


def bases_for(workspace):
    bases = {p: workspace / f'artifacts/system-hardware-followup-sheng-{release}/{p}.img'
             for p, (release, _, _) in PINNED.items()}
    for p, base in bases.items():
        assert base.is_file() and not base.is_symlink()
        assert base.stat().st_size == PINNED[p][1] and sha(base) == PINNED[p][2], p
    return bases


def validate(spec, workspace):
    assert set(spec) == {'revision', 'partitions', 'device_inputs', 'build_inputs',
                         'source_commit', 'expected_outputs', 'fs_config_sha256'}
    assert spec['revision'] == 21 and spec['expected_outputs'] == OUTPUTS
    assert set(spec['partitions']) == set(SCOPE)
    assert set(REVIEWED_SHA256) == set(SCOPE), 'The build must be reviewed first'
    for partition, stage in spec['partitions'].items():
        assert set(stage) == {'files', 'new_nodes'}
        assert set(stage['files']) == set(REVIEWED_SHA256[partition]) == SCOPE[partition]
        assert set(stage['new_nodes']) == EXPECTED_NODES[partition]
        for path, value in stage['files'].items():
            assert value['sha256'] == REVIEWED_SHA256[partition][path], path
        for path, value in stage['new_nodes'].items():
            relative_path(path)
            new_metadata(value, directory=path == 'etc/sheng')
        validate_inputs(partition, stage['files'])
    validate_packaging_inputs(spec['partitions'], spec['build_inputs'])
    assert sha(HOST / 'fs_config') == spec['fs_config_sha256']
    for path, digest in BUILD['source_sha256'].items():
        assert sha(DEVICE / path) == digest, path
    assert set(source_paths(workspace)) == set(spec['device_inputs'])
    for path, digest in spec['device_inputs'].items():
        relative_path(path)
        local, built = workspace / 'device/xiaomi/sheng' / path, DEVICE / path
        assert local.is_file() and built.is_file() and not built.is_symlink()
        assert sha(local) == sha(built) == digest, path


def ext4_nodes(base, labels):
    snapshot = ext4_snapshot(base)
    parent = snapshot['inodes'][inode_number(base, '/etc')]
    assert stat.S_ISDIR(struct.unpack_from('<H', parent)[0])
    seconds = struct.unpack_from('<I', parent, 12)[0]
    seconds += (struct.unpack_from('<I', parent, 136)[0] & 3) << 32
    inputs = ''.join('system_ext/' + p + ('/' if p == 'etc/sheng' else '') + '\n' for p in sorted(NODES))
    result = subprocess.run([HOST / 'fs_config', '-D', PRODUCT], input=inputs,
                            check=True, capture_output=True, text=True)
    parsed = {line.split()[0].removeprefix('system_ext/'): line.split()[1:]
              for line in result.stdout.splitlines()}
    assert set(parsed) == NODES
    nodes = {}
    for path, fields in parsed.items():
        directory = path == 'etc/sheng'
        assert len(fields) == 3 and fields[:2] == ['0', '0']
        mode = int(fields[2], 8)
        assert mode == (0o755 if directory else 0o644)
        label = labels.lookup('/system_ext/' + path, stat.S_IFDIR if directory else stat.S_IFREG)
        assert label == 'u:object_r:system_file:s0'
        nodes[path] = dict(uid=0, gid=0, mode=mode, mtime_ns=seconds * 1_000_000_000, selinux=label)
    return nodes


def erofs_nodes(partition, base, entries, labels):
    nodes = erofs_new_nodes(partition, base, entries, labels)
    assert set(nodes) == EXPECTED_NODES[partition]
    if nodes:
        inputs = ''.join(partition + '/' + path + '\n' for path in sorted(nodes))
        result = subprocess.run([HOST / 'fs_config', '-D', PRODUCT], input=inputs,
                                check=True, capture_output=True, text=True)
        parsed = {line.split()[0].removeprefix(partition + '/'): line.split()[1:]
                  for line in result.stdout.splitlines()}
        assert set(parsed) == set(nodes)
        for path, fields in parsed.items():
            assert len(fields) == 3
            uid, gid, mode = int(fields[0]), int(fields[1]), int(fields[2], 8)
            assert uid == 0
            assert (gid, mode) == ((2000, 0o755) if path.startswith('bin/') else (0, 0o644))
            nodes[path].update(uid=uid, gid=gid, mode=mode)
            new_metadata(nodes[path])
    return nodes


def freeze(workspace, path, bases):
    assert not path.exists(), 'Never overwrite a frozen specification'
    keys = set().union(*(erofs_input_keys(p) for p in ('odm', 'vendor')))
    keys.add('obj/PACKAGING/system_ext_intermediates/system_ext_image_info.txt')
    partitions = {}
    with CompiledContexts(packaging_input_path('@sepolicy_file_contexts').read_bytes()) as labels:
        for p, paths in SCOPE.items():
            entries = {name: dict(source=str(PRODUCT / p / name),
                                 bytes=(PRODUCT / p / name).stat().st_size,
                                 sha256=sha(PRODUCT / p / name), kind='file') for name in sorted(paths)}
            nodes = (ext4_nodes(bases[p], labels) if p == 'system_ext'
                     else erofs_nodes(p, bases[p], entries, labels))
            partitions[p] = dict(files=entries, new_nodes=nodes)
    spec = dict(revision=21, partitions=partitions,
                device_inputs={p: sha(DEVICE / p) for p in source_paths(workspace)},
                build_inputs={p: sha(packaging_input_path(p)) for p in sorted(keys)},
                fs_config_sha256=sha(HOST / 'fs_config'), expected_outputs=OUTPUTS,
                source_commit=subprocess.run(['git', '-C', workspace, 'rev-parse', 'HEAD'],
                                             check=True, capture_output=True, text=True).stdout.strip())
    validate(spec, workspace)
    with path.open('x') as stream:
        stream.write(json.dumps(spec, indent=2) + '\n')
    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--spec', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--freeze-only', action='store_true')
    mode.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    assert __debug__ and DEVICE.resolve() == (ROM / 'device/xiaomi/sheng').resolve()
    workspace = args.workspace.resolve(strict=True)
    bases = bases_for(workspace)
    spec = freeze(workspace, args.spec, bases) if args.freeze_only else json.loads(args.spec.read_text())
    validate(spec, workspace)
    digest = sha(args.spec)
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    for p in SCOPE:
        _, _, _, tree = tree_descriptor(avb, avbtool, bases[p], p)
        parent = bases['vbmeta_system' if p == 'system_ext' else 'vbmeta']
        _, _, descriptors, _ = parse_image(avb, avbtool, parent)
        selected = [d for d in descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)
                    and d.partition_name == p]
        assert len(selected) == 1 and selected[0].encode() == tree.encode(), p
    if args.freeze_only or args.validate_only:
        print(json.dumps(dict(revision=21, spec_sha256=digest, validation_passed=True)))
        return
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r21'
    assert not destination.exists(), 'Never overwrite a published batch'
    work = Path('/root/sheng-lineage/hardware-followup') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-settings-tablet-r21')
    work.mkdir(parents=True)
    reference = work / 'platform-reference.apk'
    debugfs(bases['system'], f'dump /system/framework/framework-res.apk {reference}')
    platform = certificates(reference)
    outputs, replacements, reports = {}, {}, {}
    for p, stage in spec['partitions'].items():
        arguments = p, bases[p], stage['files'], stage['new_nodes'], work, avb, avbtool
        image, tree, report = (stage_ext4(*arguments, platform) if p == 'system_ext'
                               else stage_erofs(*arguments))
        assert set(report['changed_files']) == SCOPE[p]
        outputs[p], replacements[p], reports[p] = image, tree, report
    for parent, names, algorithm in (
        ('vbmeta', ('odm', 'vendor'), 'SHA256_RSA4096'),
        ('vbmeta_system', ('system_ext',), 'SHA256_RSA2048'),
    ):
        outputs[parent] = work / (parent + '.img')
        merge_parent(avb, avbtool, bases[parent], [replacements[p] for p in names], outputs[parent], algorithm, work)
    validate(spec, workspace)
    assert sha(args.spec) == digest and set(outputs) == set(OUTPUTS)
    bases_for(workspace)
    report = dict(revision=21, frozen_spec=spec, spec_sha256=digest,
                  baseline_sha256={p: v[2] for p, v in PINNED.items()},
                  partition_reports=reports, work_dir=str(work),
                  exact_baselines_verified=True, all_filesystem_stages_verified=True,
                  both_parent_chains_verified=True, platform_certificate=platform,
                  hardware_boot_tested=False, runtime_verified=False)
    publish_batch(destination, outputs, report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
