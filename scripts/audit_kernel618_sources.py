#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record pinned reference architecture and sheng board source coverage."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def git(path, *args):
    return subprocess.run(['git', '-C', str(path), *args], check=True,
                          text=True, capture_output=True).stdout.strip()


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path('/root/sheng-618'))
    parser.add_argument('--reference', type=Path, default=project / 'tools/nuwa-k618-reference')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan_path = project / 'device/xiaomi/sheng/interfaces/kernel/6.18/source-plan.json'
    plan = json.loads(plan_path.read_text())
    if git(args.reference, 'rev-parse', 'HEAD') != plan['reference']['revision']:
        raise ValueError('Reference project differs from the pinned revision')
    if git(args.reference, 'status', '--porcelain'):
        raise ValueError('Reference project has local changes')
    receipts, trees = [], {}
    primary_names = {x['name'] for x in plan['board_sources']}
    for source in plan['board_sources'] + plan.get('supplemental_board_sources', []):
        repo = args.source_root / 'src' / source['name']
        revision = git(repo, 'rev-parse', 'HEAD')
        if revision != source['revision']:
            raise ValueError(f'Wrong source revision: {repo}')
        files = git(repo, 'ls-tree', '-r', '--name-only', revision).splitlines()
        catalog_only = all(p.name == '.git' for p in repo.iterdir())
        if not catalog_only and git(repo, 'status', '--porcelain'):
            raise ValueError(f'Source checkout has local changes: {repo}')
        trees[source['name']] = files
        receipts.append({**source, 'path': str(repo), 'checked_revision': revision,
                         'git_tree': git(repo, 'rev-parse', revision + '^{tree}'),
                         'catalog_file_count': len(files), 'full_checkout': not catalog_only,
                         'source_role': 'primary' if source['name'] in primary_names else 'tablet-supplement'})
    coverage = {}
    for label, tokens in {
        'novatek_nt36532': ['nt36532'],
        'xiaomi_touchfeature': ['touchfeature', 'xiaomi_touch.c'],
        'keyboard': ['nanosic_driver', 'xiaomi_keyboard'],
        'hall': ['xiaomi_hall'],
        'metis': ['metis'],
        'pogo_charging': ['pogochg/', 'nanosic_platform'],
        'cs35l43': ['cs35l43'],
        'fingerprint': ['fingerprint/fpc_', 'fingerprint/xiaomi_fp'],
        'tablet_panel': ['dsi-panel-n81a', 'sheng-sde-display'],
    }.items():
        matches = [{'repository': name, 'path': path}
                   for name, files in trees.items() for path in files
                   if any(token in path.lower() for token in tokens)]
        coverage[label] = {'matches': matches[:40], 'match_count': len(matches),
                           'scope': 'Filename catalog search of pinned LOS and user-approved official MiCode sheng repositories; not a global source-availability claim.'}
    evidence = []
    for file, needle in [
        ('README.zh-CN.md', '406'),
        ('kernel-6.18/k618_ports.py', 'k618 initramfs_last'),
        ('kernel-6.18/k618_timg.sh', "MR=${MADRID_ROOT"),
        ('kernel-6.18/k618_gki.sh', "KMI is the 18 Pro Max"),
        ('kernel-6.18/k618_touch.sh', 'ST FTS'),
    ]:
        data = (args.reference / file).read_bytes()
        lines = data.decode().splitlines()
        matches = [(i + 1, line) for i, line in enumerate(lines) if needle in line]
        if not matches:
            raise ValueError(f'Reference evidence missing: {file}: {needle}')
        evidence.append({'file': file, 'sha256': hashlib.sha256(data).hexdigest(),
                         'lines': [{'line': i, 'text': line} for i, line in matches],
                         'url': f"https://github.com/JiaqiLi404/android_kernel_618_for_sm8550/blob/{plan['reference']['revision']}/{file}#L{matches[0][0]}"})
    result = {'schema': 1, 'device': 'sheng', 'primary_rom': plan['primary_rom'],
              'source_plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
              'reference': plan['reference'], 'reference_evidence': evidence,
              'board_source_receipts': receipts, 'filename_coverage': coverage,
              'source_inputs_modified': False, 'device_writes': 0,
              'build_evidence': 'kernel618-build-verification.json (separate build audit)',
              'kernel618_device_validated': False,
              'missing_catalog_groups': [k for k, v in coverage.items() if v['match_count'] == 0]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'checked_repositories': len(receipts),
                      'missing_catalog_groups': result['missing_catalog_groups'],
                      'build_evidence': result['build_evidence']}))


if __name__ == '__main__':
    main()
