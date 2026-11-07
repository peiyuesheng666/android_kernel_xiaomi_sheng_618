#!/usr/bin/env python3
"""Package the reviewed r19 AON and measured battery-SOH batch over r18."""
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
    'odm': ('r18', 1141067776, 'ecc21d624a0b5c5f31552001d62d815c73d5762dc5a041af4361bce91d2e5bb5'),
    'vendor': ('r16', 303517696, 'de2ca07b44743f201bd911c11e54ce60134463c3f4e83589b6413c537e7d02de'),
    'vbmeta': ('r18', 8192, '1d6b64b741611cfab318794aa29d4a50fe4e3cde6b18c1131e310f27bd20dada'),
    'system': ('r13', 1005133824, '0551a74f4f995793665a485d10caacffb22ccd8fdaffb78d7811d17c658b3ac1'),
    'system_ext': ('r9', 572813312, '7a4e2a739f9cbc3a9713113e40f8a181dde34875c1ef0abee5e53411de58c573'),
    'vbmeta_system': ('r13', 4096, 'a947be896074811b496f42cf3759def63f808518869f56ed6c67c608622cd165'),
}
SCOPE = {
    'odm': {'overlay/FrameworkResOverlaySheng.apk', 'etc/selinux/precompiled_sepolicy'},
    'vendor': {'etc/selinux/vendor_sepolicy.cil', 'etc/selinux/vendor_service_contexts',
               'etc/selinux/vendor_file_contexts', 'etc/vintf/manifest.xml',
               'bin/hw/android.hardware.health-service.sheng',
               'etc/init/android.hardware.health-service.sheng.rc'},
    'system_ext': {'app/MiAONService/MiAONService.apk'},
}
# Reviewed combined build: signing, resources, policy, init and ELF dependencies.
REVIEWED_SHA256 = {
    "odm": {
        "etc/selinux/precompiled_sepolicy": "8317106950e7f99da8dd80691b028771c57d441752ae6ff58e6648739ce99374",
        "overlay/FrameworkResOverlaySheng.apk": "c75aa44932b9f637723fe95b7b25dec8b004c3e6d766894c3d9a8b251310483e"
    },
    "vendor": {
        "bin/hw/android.hardware.health-service.sheng": "07b3145d9ba4c1b93ad7cb3cfc11ec663a707258b3aeefb50cf6218e3c613011",
        "etc/init/android.hardware.health-service.sheng.rc": "2429ec9215c8ca47ff704415db2416cfad6dabd8063ce14e0beb9def81d38c0e",
        "etc/selinux/vendor_file_contexts": "8378fbe17737d5b36f168efd982cb7859d4d102fe197c7ee2efd55a1ac991dcf",
        "etc/selinux/vendor_sepolicy.cil": "b9849a0178c4c35bdc09e2d4d8aa87181c8421dd5a8cc2ab532c1403f4f7221a",
        "etc/selinux/vendor_service_contexts": "c07e9275cc1f43cf0b076442fd74e977f5972624e046c3087b6c3efc1200f778",
        "etc/vintf/manifest.xml": "6a94b185039d32e2d16b98efeeb8db1d91d720e82ab4226cf2bc972427e493b5"
    },
    "system_ext": {
        "app/MiAONService/MiAONService.apk": "3f5adb243442c3a5d4c88fbe35a61243f205624754d1a441a6ede27caf744625"
    }
}
OUTPUTS = {p: PINNED[p][1] for p in (*SCOPE, 'vbmeta', 'vbmeta_system')}
NODES = {'app/MiAONService', 'app/MiAONService/MiAONService.apk'}
EXPECTED_NODES = {'odm': set(), 'system_ext': NODES,
                  'vendor': {'bin/hw/android.hardware.health-service.sheng',
                             'etc/init/android.hardware.health-service.sheng.rc'}}


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
    assert spec['revision'] == 19 and spec['expected_outputs'] == OUTPUTS
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
            new_metadata(value, directory=path == 'app/MiAONService')
        validate_inputs(partition, stage['files'])
    validate_packaging_inputs(spec['partitions'], spec['build_inputs'])
    assert sha(HOST / 'fs_config') == spec['fs_config_sha256']
    assert set(source_paths(workspace)) == set(spec['device_inputs'])
    for path, digest in spec['device_inputs'].items():
        relative_path(path)
        local, built = workspace / 'device/xiaomi/sheng' / path, DEVICE / path
        assert local.is_file() and built.is_file() and not built.is_symlink()
        assert sha(local) == sha(built) == digest, path


def ext4_nodes(base, labels):
    snapshot = ext4_snapshot(base)
    parent = snapshot['inodes'][inode_number(base, '/app')]
    assert stat.S_ISDIR(struct.unpack_from('<H', parent)[0])
    seconds = struct.unpack_from('<I', parent, 12)[0]
    seconds += (struct.unpack_from('<I', parent, 136)[0] & 3) << 32
    result = subprocess.run([HOST / 'fs_config', '-D', PRODUCT],
                            input='system_ext/app/MiAONService/\nsystem_ext/app/MiAONService/MiAONService.apk\n',
                            check=True, capture_output=True, text=True)
    parsed = {line.split()[0].removeprefix('system_ext/'): line.split()[1:]
              for line in result.stdout.splitlines()}
    assert set(parsed) == NODES
    nodes = {}
    for path, fields in parsed.items():
        directory = path == 'app/MiAONService'
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
    spec = dict(revision=19, partitions=partitions,
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
        print(json.dumps(dict(revision=19, spec_sha256=digest, validation_passed=True)))
        return
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r19'
    assert not destination.exists(), 'Never overwrite a published batch'
    work = Path('/root/sheng-lineage/hardware-followup') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-aon-health-r19')
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
    report = dict(revision=19, frozen_spec=spec, spec_sha256=digest,
                  baseline_sha256={p: v[2] for p, v in PINNED.items()},
                  partition_reports=reports, work_dir=str(work),
                  exact_baselines_verified=True, all_filesystem_stages_verified=True,
                  both_parent_chains_verified=True, platform_certificate=platform,
                  hardware_boot_tested=False, runtime_verified=False)
    publish_batch(destination, outputs, report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
