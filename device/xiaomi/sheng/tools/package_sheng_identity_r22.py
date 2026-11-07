#!/usr/bin/env python3
"""Package r22 Settings, reset-name resources and ordered tablet classpath."""
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
    'odm': ('r21', 1141067776, '474e3ceab0be4a75847adce0f0dc44f2793274f7b74587501522cfd6ccb9ffa5'),
    'vendor': ('r21', 303517696, '210bf6f64bc865a8f6834e5b4b1d6fdd965139fec2cef2fda56b9fe978d5fd27'),
    'vbmeta': ('r21', 8192, 'e1fa13fa8e27976ea2748f0f52714647b8e275ab1f9130388dab1705525a9fb0'),
    'system': ('r20', 1005133824, '0f9c8ad6341faae4abaa9c080614d6d879aa62e85e36383086bb0333adfb4dce'),
    'vbmeta_system': ('r20', 4096, 'bb396433319e6d1f77cb24f6f223b08de107d6e266838bc156c81acf526374e8'),
    'system_ext': ('r19', 572813312, '9663016b59a90b30cb573dd45785f01ef1ef0ccefad6572279051cdec92a220a'),
}
# The r20-compatible system_ext base omits r21's obsolete etc/sheng fragment.
# Its only r21 additions were the compatibility JAR, init override and fragment.
SCOPE = {
    'odm': {'overlay/SettingsResOverlaySheng.apk', 'overlay/SettingsProviderResOverlaySheng.apk',
            'etc/selinux/precompiled_sepolicy',
            'etc/selinux/precompiled_sepolicy.system_ext_sepolicy_and_mapping.sha256'},
    'system_ext': {'framework/sheng-tablet-compat.jar', 'etc/init/sheng-tablet-compat.rc',
                   'bin/sheng-derive-classpath', 'etc/selinux/system_ext_file_contexts',
                   'etc/selinux/system_ext_sepolicy.cil',
                   'etc/selinux/system_ext_sepolicy_and_mapping.sha256'},
}
BUILD = json.loads((DEVICE / 'docs/build-r22-identity-tablet-20261107.json').read_text())
assert BUILD['build_passed'] and BUILD['resource_link_probe_passed'] and BUILD['classpath_adapter_tests_passed']
REVIEWED_SHA256 = BUILD['reviewed_sha256']
OUTPUTS = {p: PINNED[p][1] for p in (*SCOPE, 'vbmeta', 'vbmeta_system')}
NODES = {'framework/sheng-tablet-compat.jar', 'etc/init/sheng-tablet-compat.rc', 'bin/sheng-derive-classpath'}
EXPECTED_NODES = {'odm': {'overlay/SettingsProviderResOverlaySheng.apk'}, 'system_ext': NODES}
# The new ODM RRO uses the same test-key certificate as the existing Settings RRO.
NEW_OVERLAY_CERTIFICATES = {
    'overlay/SettingsProviderResOverlaySheng.apk': [
        'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'],
}




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
    assert spec['revision'] == 22 and spec['expected_outputs'] == OUTPUTS
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
            new_metadata(value)
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
    inputs = ''.join('system_ext/' + p + '\n' for p in sorted(NODES))
    result = subprocess.run([HOST / 'fs_config', '-D', PRODUCT], input=inputs,
                            check=True, capture_output=True, text=True)
    parsed = {line.split()[0].removeprefix('system_ext/'): line.split()[1:]
              for line in result.stdout.splitlines()}
    assert set(parsed) == NODES
    nodes = {}
    for path, fields in parsed.items():
        executable = path == 'bin/sheng-derive-classpath'
        assert len(fields) == 3
        uid, gid, mode = int(fields[0]), int(fields[1]), int(fields[2], 8)
        assert (uid, gid, mode) == ((0, 2000, 0o755) if executable else (0, 0, 0o644))
        label = labels.lookup('/system_ext/' + path, stat.S_IFREG)
        assert label == ('u:object_r:derive_classpath_exec:s0' if executable else 'u:object_r:system_file:s0')
        nodes[path] = dict(uid=uid, gid=gid, mode=mode, mtime_ns=seconds * 1_000_000_000, selinux=label)
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
    keys = erofs_input_keys('odm')
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
    spec = dict(revision=22, partitions=partitions,
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
        print(json.dumps(dict(revision=22, spec_sha256=digest, validation_passed=True)))
        return
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r22'
    assert not destination.exists(), 'Never overwrite a published batch'
    work = Path('/root/sheng-lineage/hardware-followup') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-identity-tablet-r22')
    work.mkdir(parents=True)
    reference = work / 'platform-reference.apk'
    debugfs(bases['system'], f'dump /system/framework/framework-res.apk {reference}')
    platform = certificates(reference)
    outputs, replacements, reports = {}, {}, {}
    for p, stage in spec['partitions'].items():
        arguments = p, bases[p], stage['files'], stage['new_nodes'], work, avb, avbtool
        image, tree, report = (stage_ext4(*arguments, platform) if p == 'system_ext'
                               else stage_erofs(*arguments, new_apk_certificates=NEW_OVERLAY_CERTIFICATES))
        assert set(report['changed_files']) == SCOPE[p]
        outputs[p], replacements[p], reports[p] = image, tree, report
    for parent, names, algorithm in (
        ('vbmeta', ('odm',), 'SHA256_RSA4096'),
        ('vbmeta_system', ('system_ext',), 'SHA256_RSA2048'),
    ):
        outputs[parent] = work / (parent + '.img')
        merge_parent(avb, avbtool, bases[parent], [replacements[p] for p in names], outputs[parent], algorithm, work)
    validate(spec, workspace)
    assert sha(args.spec) == digest and set(outputs) == set(OUTPUTS)
    bases_for(workspace)
    report = dict(revision=22, frozen_spec=spec, spec_sha256=digest,
                  baseline_sha256={p: v[2] for p, v in PINNED.items()},
                  partition_reports=reports, work_dir=str(work),
                  exact_baselines_verified=True, all_filesystem_stages_verified=True,
                  both_parent_chains_verified=True, platform_certificate=platform,
                  hardware_boot_tested=False, runtime_verified=False)
    publish_batch(destination, outputs, report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
