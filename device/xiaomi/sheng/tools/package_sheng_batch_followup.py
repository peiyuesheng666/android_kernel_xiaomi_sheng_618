#!/usr/bin/env python3
"""Package r13 from a reviewed, hash-frozen list of installed build outputs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from package_sheng_batch_helpers import (
    certificates, debugfs, merge_parent, publish_batch, relative_path,
    stage_erofs, stage_ext4, tree_descriptor, validate_inputs, validate_packaging_inputs,
)
from package_sheng_model_followup import PRODUCT, ROM, parse_image, sha
from package_sheng_overlay_followup import BASELINES, INHERITED, SYSTEM_DEFAULTS_BYTES

DEVICE = Path(__file__).resolve().parents[1]
PINNED = dict(INHERITED)
PINNED.update(odm=('r11', BASELINES[12]['odm_sha256']),
              vbmeta=('r11', BASELINES[12]['vbmeta_sha256']))
FPC_ALIAS = 'lib64/hw/fingerprint.fpc.default.so'
FPC_TARGET_SHA256 = '4388432669c5fe1cc52ebd5a343d190724a2417f60352a804b43b0900939bcbd'
COLOR_DEVICE_INPUTS = {'configs/display/color/' + p for p in (
    'Android.bp', 'snapdragon_color_libs_config.xml', 'df_default.xml', 'provenance.json')}
VENDOR_SEPOLICY_FILES = {f'etc/selinux/{n}' for n in (
    'genfs_labels_version.txt', 'plat_pub_versioned.cil', 'plat_sepolicy_vers.txt',
    'selinux_denial_metadata', 'vendor_file_contexts', 'vendor_hwservice_contexts',
    'vendor_keystore2_key_contexts', 'vendor_mac_permissions.xml', 'vendor_property_contexts',
    'vendor_seapp_contexts', 'vendor_sepolicy.cil', 'vendor_service_contexts',
    'vendor_tee_service_contexts', 'vndservice_contexts')}
REQUIRED = {
    'system': {'etc/device-config-defaults'},
    'odm': {'overlay/FrameworkResOverlaySheng.apk', 'etc/selinux/precompiled_sepolicy',
            FPC_ALIAS} |
           {f'etc/selinux/precompiled_sepolicy.{p}_sepolicy_and_mapping.sha256'
            for p in ('plat', 'product', 'system_ext')},
    'vendor': {'etc/snapdragon_color_libs_config.xml', 'etc/df_default.xml',
               'build.prop', 'etc/init/init.sm8550.rc'} | VENDOR_SEPOLICY_FILES,
}
ALLOWED = {partition: set(paths) for partition, paths in REQUIRED.items()}


def load_spec(path):
    spec = json.loads(path.read_text())
    assert set(spec) == {'revision', 'partitions', 'device_inputs', 'build_inputs', 'expected_outputs'}
    assert spec['revision'] == 13
    assert set(spec['partitions']) == set(REQUIRED)
    expected = set(spec['partitions']) | {'vbmeta', 'vbmeta_system'}
    assert set(spec['expected_outputs']) == expected and len(spec['expected_outputs']) == len(expected) == 5
    for partition, stage in spec['partitions'].items():
        assert set(stage) == {'files', 'new_nodes'}
        assert REQUIRED[partition] <= set(stage['files']) <= ALLOWED[partition]
        assert set(stage['new_nodes']) <= {
            str(parent) for name in stage['files']
            for parent in [Path(name)] + list(Path(name).parents) if str(parent) != '.'}
        validate_inputs(partition, stage['files'], allow_symlinks=partition in ('odm', 'vendor'))
    alias = spec['partitions']['odm']['files'][FPC_ALIAS]
    assert alias.get('kind') == 'symlink' and alias['link_target'] == 'fingerprint.fpc.so'
    assert alias['target_sha256'] == FPC_TARGET_SHA256
    assert spec['device_inputs'] and spec['build_inputs'], 'Freeze DT and packaging inputs as well'
    assert {'Android.bp', 'device.mk', 'lineage_sheng.mk', 'rootdir/etc/init.sm8550.rc', 'sepolicy/vendor/file_contexts',
            'tools/publish_sheng_batch_windows.ps1'} | COLOR_DEVICE_INPUTS <= set(spec['device_inputs'])
    for relative, digest in spec['device_inputs'].items():
        target = DEVICE / relative_path(relative)
        assert target.is_file() and not target.is_symlink()
        assert target.resolve().is_relative_to(DEVICE.resolve()) and sha(target) == digest
    validate_packaging_inputs(spec['partitions'], spec['build_inputs'])
    assert (PRODUCT / 'system/etc/device-config-defaults').read_bytes() == SYSTEM_DEFAULTS_BYTES
    return spec


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError('Never run packaging with Python assertions disabled')
    workspace = args.workspace.resolve()
    spec_path = args.spec.resolve()
    spec_digest = sha(spec_path)
    spec = load_spec(spec_path)
    bases = {p: workspace / f'artifacts/system-hardware-followup-sheng-{release}/{p}.img'
             for p, (release, _) in PINNED.items()}
    for partition, image in bases.items():
        assert image.is_file() and sha(image) == PINNED[partition][1], partition
    sys.path.insert(0, str(ROM / 'external/avb'))
    import avbtool
    avb = avbtool.Avb()
    for partition in spec['partitions']:
        _, _, _, descriptor = tree_descriptor(avb, avbtool, bases[partition], partition)
        parent = bases['vbmeta'] if partition in ('odm', 'vendor') else bases['vbmeta_system']
        _, _, descriptors, _ = parse_image(avb, avbtool, parent)
        matches = [d for d in descriptors if isinstance(d, avbtool.AvbHashtreeDescriptor)
                   and d.partition_name == partition]
        assert len(matches) == 1 and matches[0].encode() == descriptor.encode(), partition
    if args.validate_only:
        print(json.dumps(dict(revision=13, spec_sha256=spec_digest, readonly_validation_passed=True), indent=2))
        return
    destination = workspace / 'artifacts/system-hardware-followup-sheng-r13'
    assert not destination.exists(), 'Never overwrite an existing revision'
    work = Path('/root/sheng-lineage/hardware-followup') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-batch-r13')
    work.mkdir(parents=True)
    certificate_apk = work / 'baseline-framework-res.apk'
    debugfs(bases['system'], f'dump /system/framework/framework-res.apk {certificate_apk}')
    platform_certificate = certificates(certificate_apk)
    outputs, replacements, reports = {}, {}, {}
    for partition, stage in spec['partitions'].items():
        arguments = (partition, bases[partition], stage['files'], stage['new_nodes'], work, avb, avbtool)
        image, descriptor, report = (stage_erofs(*arguments) if partition in ('odm', 'vendor')
                                     else stage_ext4(*arguments, platform_certificate))
        outputs[partition], replacements[partition], reports[partition] = image, descriptor, report
    for parent, names, algorithm in (
        ('vbmeta', ('odm', 'vendor'), 'SHA256_RSA4096'),
        ('vbmeta_system', ('system', 'system_ext'), 'SHA256_RSA2048'),
    ):
        selected = [replacements[p] for p in names if p in replacements]
        target = work / (parent + '.img')
        merge_parent(avb, avbtool, bases[parent], selected, target, algorithm, work)
        outputs[parent] = target
    assert set(outputs) == set(spec['expected_outputs'])
    assert sha(spec_path) == spec_digest and load_spec(spec_path) == spec
    for partition, base in bases.items():
        assert sha(base) == PINNED[partition][1], 'A baseline changed during packaging'
    report = dict(revision=13, spec_sha256=spec_digest, frozen_spec=spec,
                  work_dir=str(work), baseline_sha256={p: v[1] for p, v in PINNED.items()},
                  partition_reports=reports, exact_baselines_verified=True,
                  all_filesystem_stages_verified=True, both_parent_chains_verified=True,
                  hardware_boot_tested=False, runtime_verified=False)
    publish_batch(destination, outputs, report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
