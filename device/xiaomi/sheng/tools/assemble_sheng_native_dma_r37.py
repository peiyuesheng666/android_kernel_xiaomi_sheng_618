#!/usr/bin/env python3
"""Validate and assemble only the native DMA heap property over installed r36."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

from package_sheng_model_followup import PRODUCT, ROM, sha

DEVICE = Path(__file__).resolve().parents[1]
PROP = b'vendor.gralloc.use_dma_buf_heaps=true\n'
BASELINE = '264883ef0a6486d9861ec1d94db4fb7f0d6a639d242184be66064ca79bba8834'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--probe-review', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__ and DEVICE == ROM / 'device/xiaomi/sheng'
    audit = json.loads(args.audit.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert len(audit['repositories']) == 25
    assert all(r['passed'] and r['fetch']['returncode'] == 0 for r in audit['repositories'])
    probe = json.loads(args.probe_review.read_text())
    assert probe['native_secure_heap_probe_passed'] is True
    assert probe['camera_opened'] is False and probe['protected_pixels_mapped'] is False
    assert probe['native_secure_allocations'] == 2
    source = DEVICE / 'properties/vendor.prop'
    assert source.read_bytes().count(PROP) == 1
    target = PRODUCT / 'vendor/build.prop'
    assert target.is_file() and not target.is_symlink() and sha(target) == BASELINE
    old = target.read_bytes()
    assert PROP.split(b'=')[0] not in old
    work = args.work
    assert work.is_absolute() and work.parent.resolve(strict=True) == Path('/root/sheng-lineage/hardware-diagnostics')
    assert not work.exists()
    work.mkdir()
    shutil.copyfile(target, work / 'vendor-original.prop')
    updated = old + b'\n' + PROP
    checked = work / 'vendor-native-dma.prop'
    checked.write_bytes(updated)
    script = ROM / 'build/make/tools/post_process_props.py'
    sys.path[:0] = [str(script.parent), str(ROM / 'build/soong/scripts')]
    spec = importlib.util.spec_from_file_location('sheng_dma_property_validation', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    props = module.PropList(str(checked))
    assert module.override_optional_props(props, False)
    assert module.validate_grf_props(props) and module.validate(props)
    assert not any(p.is_optional() for p in props.get_all_props())
    target.write_bytes(updated)
    review = dict(revision=37, scoped_configuration_assembly_passed=True,
        platform_build_property_validation_passed=True, native_secure_heap_probe_passed=True,
        full_product_build_passed=False, normal_product_module_build_passed=False,
        baseline_vendor_build_prop_sha256=BASELINE,
        property_delta={'added': {'vendor.gralloc.use_dma_buf_heaps': 'true'}, 'removed': [], 'changed': []},
        reviewed_sha256={'vendor': {'build.prop': sha(target)}},
        source_sha256={p: sha(DEVICE / p) for p in (
            'properties/vendor.prop', 'tools/assemble_sheng_native_dma_r37.py')},
        native_probe_review_sha256=sha(args.probe_review), prebuild_public_audit_sha256=sha(args.audit),
        public_repositories_fresh_audited=25, all_project_status_checked=audit['project_count'],
        property_validation_source_sha256=sha(script), postbuild_public_audit_passed=False,
        installed=False, runtime_verified=False, systemui_changed=False)
    output = DEVICE / 'docs/r37-native-dma-build-review-20261108.json'
    assert not output.exists()
    output.write_text(json.dumps(review, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    main()
