#!/usr/bin/env python3
"""Assemble two reviewed policy files; no full graph build or device operation."""
import hashlib
import json
from pathlib import Path
import shutil

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
DIAG = Path('/root/sheng-lineage/hardware-diagnostics')
PRODUCT = ROM / 'out/target/product/sheng'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert __debug__ and DEVICE == ROM / 'device/xiaomi/sheng'
    audit = DIAG / 'r35-prebuild-audit-20261108.json'
    audited = json.loads(audit.read_text())
    assert audited['known_public_sources_passed'] and not audited['all_project_nonclean_status']
    assert all(r['passed'] and r['fetch']['returncode'] == 0 for r in audited['repositories'])
    work = DIAG / 'r35-policy-candidates-20261108'
    built = json.loads((work / 'build-result.json').read_text())
    assert built['scoped_policy_build_passed'] and built['neverallow_checks_enabled']
    delta_path = DIAG / 'r35-policy-delta-20261108/policy-delta.json'
    delta = json.loads(delta_path.read_text())
    assert delta['added_existing_type_permissions'] == [dict(kind='allow', source='cameraserver',
        target='hal_miface_default', tclass='binder', permission='call')]
    for key in ['added_types', 'removed_types', 'removed_existing_type_permissions',
        'existing_type_attribute_membership_changes', 'existing_type_non_av_rule_forms_added',
        'existing_type_non_av_rule_forms_removed', 'existing_role_type_statements_added',
        'existing_role_type_statements_removed', 'other_statements_added', 'other_statements_removed']:
        assert not delta[key], key
    assert delta['baseline_permissive_domains'] == delta['candidate_permissive_domains']
    for filename, digest in delta['inputs_and_decompiled_sha256'].items():
        assert sha(Path(filename)) == digest
    targets = {
        'vendor': ('etc/selinux/vendor_sepolicy.cil', 'vendor_sepolicy.cil',
                   '529d61219505e173d04e10d617a6349e3d77c97fcd13a28e7ffb0da0cbb4ce07'),
        'odm': ('etc/selinux/precompiled_sepolicy', 'precompiled_sepolicy',
                '85b032453940d401a69b216a5af221c35d9473d3bb825cd71cfd3364938e5ef1'),
    }
    reviewed = {}
    for partition, (relative, filename, baseline) in targets.items():
        source = work / filename
        target = PRODUCT / partition / relative
        assert sha(target) == baseline and sha(source) == built['outputs'][filename]['sha256']
        shutil.copyfile(source, target)
        assert sha(target) == sha(source)
        reviewed[partition] = {relative: sha(source)}
    sources = ['sepolicy/vendor/hal_miface_default.te', 'tools/build_sheng_policy_candidates.py',
               'tools/review_sheng_policy_delta.py', 'tools/assemble_sheng_face_callback_r35.py']
    report = dict(revision=35, scoped_module_build_passed=True, scoped_policy_build_passed=True,
        full_product_build_passed=False, normal_product_module_build_passed=False,
        neverallow_checks_enabled=True, exact_one_callback_permission_added=True,
        source_sha256={name: sha(DEVICE / name) for name in sources}, reviewed_sha256=reviewed,
        prebuild_audit_sha256=sha(audit), policy_build_report_sha256=sha(work / 'build-result.json'),
        policy_command_log_sha256=sha(work / 'commands.json'), policy_delta_sha256=sha(delta_path),
        baseline_policy_sha256=targets['odm'][2], systemui_changed=False,
        installed=False, runtime_verified=False)
    output = DEVICE / 'docs/r35-face-callback-build-review-20261108.json'
    assert not output.exists()
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
