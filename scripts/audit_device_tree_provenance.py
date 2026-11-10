#!/usr/bin/env python3
"""Read-only provenance checks against the available local reference checkouts.

Run in WSL. Only the JSON audit report is written; sources are never changed.
Whole-file equality and shared lines do not, by themselves, establish authorship.
"""
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess

WORK = Path(__file__).resolve().parents[1]
DEVICE = WORK / 'device/xiaomi/sheng'
ROM = Path('/root/sheng-lineage/lineage-24.0')
REFERENCES = {
    'lineage_common': Path('/root/sheng-source-inputs/reference/lineage-common'),
    'piano': Path('/root/sheng-source-inputs/reference/piano-device'),
    'community_sheng': Path('/root/sheng-source-inputs/reference/sheng-device-reference'),
    'twrp_sheng': Path('/root/sheng-lineage/reference/twrp-sheng'),
}


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args],
                            capture_output=True, check=True)
    return result.stdout.decode('utf-8', errors='replace').strip()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(data):
    return data.replace(b'\r\n', b'\n')


def significant_lines(data):
    text = data.decode('utf-8', errors='replace')
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.strip().startswith(('#', '//', '*', '<!--'))]


def main():
    receipt = json.loads((WORK / 'reports/standalone-migration.json').read_text())
    source_files = {}
    metadata = {}
    for name, root in REFERENCES.items():
        listed = git(root, 'ls-files', '-z').split('\0')
        files = {}
        missing = []
        for relative in filter(None, listed):
            path = root / relative
            if path.is_file():
                files[relative] = path.read_bytes()
            else:
                missing.append(relative)
        source_files[name] = files
        metadata[name] = {
            'path': str(root), 'commit': git(root, 'rev-parse', 'HEAD'),
            'origin': git(root, 'remote', 'get-url', 'origin'),
            'working_tree_status': git(root, 'status', '--porcelain'),
            'tracked_file_count': len(files) + len(missing),
            'available_file_count': len(files), 'unavailable_files': missing,
        }

    common = source_files['lineage_common']
    assert metadata['lineage_common']['commit'] == receipt['source_reference_commit']
    assert not metadata['lineage_common']['working_tree_status']
    migration = []
    for entry in receipt['licensed_platform_inputs']:
        original = common[entry['source']]
        assert digest(original) == entry['source_sha256'], entry['source']
        path = DEVICE / entry['destination']
        current = path.read_bytes() if path.is_file() else None
        migration.append({
            **entry, 'source_hash_verified': True,
            'current_sha256': digest(current) if current is not None else None,
            'current_relation': ('missing' if current is None else
                                 'identical' if normalized(current) == normalized(original)
                                 else 'modified'),
        })

    indices = {}
    for name, files in source_files.items():
        index = {}
        for relative, data in files.items():
            index.setdefault(digest(normalized(data)), []).append(relative)
        indices[name] = index

    inventory = []
    for path in sorted(DEVICE.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        data = path.read_bytes()
        key = digest(normalized(data))
        text = data.decode('utf-8', errors='replace') if b'\0' not in data else ''
        matches = {name: index[key] for name, index in indices.items() if key in index}
        relative = path.relative_to(DEVICE).as_posix()
        live = ROM / 'device/xiaomi/sheng' / relative
        inventory.append({
            'file': relative, 'bytes': len(data), 'sha256': digest(data),
            'lf_normalized_sha256': key, 'exact_reference_matches': matches,
            'copyright_or_license_lines': [line.strip() for line in text.splitlines()
                if re.search(r'Copyright|SPDX-|Licensed under|Changes from Qualcomm', line)],
            'wsl_source_relation': ('missing' if not live.is_file() else
                'identical' if normalized(live.read_bytes()) == normalized(data) else 'different'),
        })

    includes = []
    for path in sorted(DEVICE.rglob('*.mk')):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if 'inherit-product' in line or re.match(r'^-?include\s', line):
                includes.append({'file': path.relative_to(DEVICE).as_posix(),
                                 'line': number, 'statement': line})
    other_xiaomi_includes = [row for row in includes
        if re.search(r'(?:device|vendor)/xiaomi/(?!sheng(?:/|\b))', row['statement'])]
    assert not other_xiaomi_includes, other_xiaomi_includes

    comparisons = []
    for own, upstream in [('BoardConfig.mk', 'BoardConfigCommon.mk'),
                          ('extract-files.py', 'extract-files.py'),
                          ('device.mk', 'common.mk'), ('Android.bp', 'Android.bp'),
                          ('rootdir/Android.bp', 'init/Android.bp')]:
        if upstream not in common:
            continue
        left = significant_lines((DEVICE / own).read_bytes())
        right = significant_lines(common[upstream])
        matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
        blocks = [block for block in matcher.get_matching_blocks() if block.size]
        comparisons.append({'file': own, 'reference_file': upstream,
                            'current_significant_lines': len(left),
                            'reference_significant_lines': len(right),
                            'ordered_shared_significant_lines': sum(b.size for b in blocks),
                            'largest_shared_block_lines': max((b.size for b in blocks), default=0),
                            'interpretation': 'Supporting comparison; not an originality percentage.'})

    stock = json.loads((WORK / 'reports/sheng-stock-preparation.json').read_text())
    stock_configs = []
    for entry in stock['copied_configuration']:
        source = Path('/root/sheng-lineage/firmware-dump/extract-source') / entry['source']
        current = DEVICE / entry['target']
        source_data = source.read_bytes()
        stock_configs.append({**entry, 'source_hash_verified': digest(source_data) == entry['sha256'],
            'current_relation': 'identical' if normalized(current.read_bytes()) == normalized(source_data)
                                else 'modified'})
    assert all(row['source_hash_verified'] for row in stock_configs)

    touch = DEVICE / 'configs/touch/sheng-touch-report'
    stock_touch = Path('/root/sheng-lineage/firmware-dump/partitions/odm/bin/touch_report_debug')
    touch_check = {'stock_path': str(stock_touch), 'current_path': str(touch),
                   'stock_sha256': digest(stock_touch.read_bytes()),
                   'current_sha256': digest(touch.read_bytes()),
                   'matches_documented_path_patch': touch.read_bytes() == stock_touch.read_bytes().replace(
                       b'/vendor/firmware/', b'/odm/firmware////')}
    assert touch_check['matches_documented_path_patch']

    report = {
        'date': '2026-11-06', 'workspace_baseline_commit': git(WORK, 'rev-parse', 'HEAD'),
        'scope': 'Current workspace device tree, local checkouts, migration script and stock receipts.',
        'references': metadata, 'device_file_count': len(inventory),
        'migration_entry_count': len(migration),
        'migration_current_counts': {kind: sum(row['current_relation'] == kind for row in migration)
                                     for kind in ('identical', 'modified', 'missing')},
        'exact_match_counts': {name: sum(name in row['exact_reference_matches'] for row in inventory)
                               for name in REFERENCES},
        'wsl_source_counts': {kind: sum(row['wsl_source_relation'] == kind for row in inventory)
                              for kind in ('identical', 'different', 'missing')},
        'runtime_other_xiaomi_device_includes': other_xiaomi_includes,
        'legacy_common_device_exists': (ROM / 'device/xiaomi/sm8550-common').exists(),
        'legacy_common_vendor_exists': (ROM / 'vendor/xiaomi/sm8550-common').exists(),
        'makefile_includes': includes, 'migration_inputs': migration,
        'upstream_line_comparisons': comparisons, 'stock_configuration_checks': stock_configs,
        'stock_touch_binary_check': touch_check, 'device_inventory': inventory,
        'limitations': [
            'No complete commit history exists before the initial workspace baseline.',
            'Available reference checkouts are finite and may be sparse; all unavailable paths are listed.',
            'Common upstream code and stock hardware data can match several repositories.',
            'Equality or similarity cannot identify which repository originally supplied a file.',
            'No claim of zero external code, original authorship of every file, or complete license compliance.',
        ],
    }
    output = WORK / 'reports/device-tree-provenance-audit.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in (
        'device_file_count', 'migration_entry_count', 'migration_current_counts',
        'exact_match_counts', 'wsl_source_counts', 'legacy_common_device_exists',
        'legacy_common_vendor_exists', 'upstream_line_comparisons')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
