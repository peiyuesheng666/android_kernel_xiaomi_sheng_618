#!/usr/bin/env python3
"""Fingerprint sheng configuration and BSP inputs for validation receipts."""
import hashlib
from pathlib import Path
import subprocess

ROM = Path('/root/sheng-lineage/lineage-24.0')


def fingerprint():
    files = []
    for directory in ('device/xiaomi/sheng', 'device/xiaomi/sheng-kernel'):
        files.extend(p for p in (ROM / directory).rglob('*')
                     if p.is_file() and not {'.git', '__pycache__'} & set(p.parts))
    files.extend(ROM / relative for relative in (
        'vendor/xiaomi/sheng/Android.bp',
        'vendor/xiaomi/sheng/Android.mk',
        'vendor/xiaomi/sheng/BoardConfigVendor.mk',
        'vendor/xiaomi/sheng/sheng-vendor.mk',
        'hardware/qcom-caf/sm8550/audio/pal/Android.bp',
        'hardware/qcom-caf/sm8550/audio/graphservices/gsl/Android.bp',
    ))
    result = {'files': {}, 'kernel_sources': {}}
    for file in sorted(set(files)):
        digest = hashlib.sha256()
        with file.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        result['files'][str(file.relative_to(ROM))] = digest.hexdigest()
    for relative in ('kernel/xiaomi/sm8550', 'kernel/xiaomi/sm8550-modules',
                     'kernel/xiaomi/sm8550-devicetrees'):
        git = ['git', '-C', str(ROM / relative)]
        revision = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
        diff = subprocess.check_output(git + ['diff', '--binary', 'HEAD', '--'])
        result['kernel_sources'][relative] = {
            'revision': revision, 'tracked_diff_sha256': hashlib.sha256(diff).hexdigest(),
        }
    return result
