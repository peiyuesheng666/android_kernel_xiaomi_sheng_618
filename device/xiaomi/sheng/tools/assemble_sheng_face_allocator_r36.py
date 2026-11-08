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
    audit = DIAG / 'r36-prebuild-audit-20261108.json'
    audited = json.loads(audit.read_text())
    assert audited['known_public_sources_passed'] and not audited['all_project_nonclean_status']
    assert all(r['passed'] and r['fetch']['returncode'] == 0 for r in audited['repositories'])
    work = DIAG / 'r36-policy-candidates-20261108'
    built = json.loads((work / 'build-result.json').read_text())
    assert built['scoped_policy_build_passed'] and built['neverallow_checks_enabled']
    delta_path = DIAG / 'r36-policy-delta-20261108/policy-delta.json'
    delta = json.loads(delta_path.read_text())
    expected = set()
    def permit(source, target, tclass, *permissions):
        for permission in permissions:
            expected.add(('allow', source, target, tclass, permission))
    client, allocator = 'hal_miface_default', 'hal_graphics_allocator_default'
    permit(allocator, client, 'binder', 'transfer')
    permit(client, allocator, 'binder', 'call', 'transfer')
    for source, target in [(allocator, client), (client, allocator)]:
        permit(source, target, 'memfd_file', 'getattr', 'map', 'read', 'write')
    permit(client, 'hal_graphics_allocator_hwservice', 'hwservice_manager', 'find')
    permit(client, 'hidl_manager_hwservice', 'hwservice_manager', 'find')
    permit(client, 'hal_graphics_allocator_service', 'service_manager', 'find')
    permit(client, 'hal_graphics_mapper_service', 'service_manager', 'find')
    permit(client, 'servicemanager', 'binder', 'call', 'transfer')
    permit(client, 'servicemanager', 'fd', 'use')
    actual = {tuple(row[k] for k in ['kind', 'source', 'target', 'tclass', 'permission'])
              for row in delta['added_existing_type_permissions']}
    assert actual == expected and len(actual) == 18
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
                   '74737f6c5e782fd470ffe9e5f1dc1ea0ca0ce3ab60d6494df1537692d9ef8a32'),
        'odm': ('etc/selinux/precompiled_sepolicy', 'precompiled_sepolicy',
                '4ad365f8228429c4444a4d6491cb45ffb9d0001363958050c88ffe017e395f44'),
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
               'tools/review_sheng_policy_delta.py', 'tools/assemble_sheng_face_allocator_r36.py']
    report = dict(revision=36, scoped_module_build_passed=True, scoped_policy_build_passed=True,
        full_product_build_passed=False, normal_product_module_build_passed=False,
        neverallow_checks_enabled=True, allocator_client_permission_delta_reviewed=True,
        source_sha256={name: sha(DEVICE / name) for name in sources}, reviewed_sha256=reviewed,
        prebuild_audit_sha256=sha(audit), policy_build_report_sha256=sha(work / 'build-result.json'),
        policy_command_log_sha256=sha(work / 'commands.json'), policy_delta_sha256=sha(delta_path),
        baseline_policy_sha256=targets['odm'][2], systemui_changed=False,
        installed=False, runtime_verified=False)
    output = DEVICE / 'docs/r36-face-allocator-build-review-20261108.json'
    assert not output.exists()
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
