#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record real pre/post-build FastRPC imports and the captured failure path."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from audit_kernel618_modules import ElfModule
from build_sheng618_upstream import K618, PROJECT, ROOT, UPSTREAM
from sheng618_fastrpc_config import REQUIRED_IMPORTS, verify_imports


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--tag', default='hardware-r35')
    options = parser.parse_args()
    assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}', options.tag)
    prior = ROOT / 'diagnostic/hardware-r34/layer/lib/modules/frpc-adsprpc.ko'
    reference = ROOT / 'diagnostic/tablet-r20/layer/lib/modules/frpc-adsprpc.ko'
    current = K618 / 'vendor/xiaomi/adsprpc-515/frpc-adsprpc.ko'
    old = ElfModule(prior)
    missing = sorted(set(REQUIRED_IMPORTS) - old.undefined())
    assert 'mem_buf_dma_buf_exclusive_owner' in missing
    try:
        verify_imports(prior)
    except ValueError as error:
        rejection = str(error)
    else:
        raise AssertionError('The gate accepted the known broken r34 provider')
    checks = [verify_imports(reference), verify_imports(current)]
    references = []
    for repository, root, files in (
        ('selected-sm8550-integration', UPSTREAM, ['kernel-6.18/k618_rpc515.sh']),
        ('LineageOS-sm8550-nuwa', ROOT / 'src/lineage-kernel', ['include/linux/mem-buf.h']),
        ('selected-soc-provider', K618 / 'soc', ['include/linux/mem-buf.h',
            'drivers/soc/qcom/mem_buf/mem_buf_dma_buf.c']),
    ):
        revision = subprocess.check_output(['git', '-C', root, 'rev-parse', 'HEAD'], text=True).strip()
        references.append(dict(repository=repository, commit=revision,
            files={name: sha(root / name) for name in files}))
    captures = {p.name: dict(bytes=p.stat().st_size, sha256=sha(p))
                for p in options.capture.glob('*') if p.is_file()}
    texts = list(options.capture.glob('*-text/bugreport-*.txt'))
    assert len(texts) == 1
    text = texts[0].read_text(errors='replace')
    kernel = text.split('------ KERNEL LOG (dmesg) ------', 1)[1].split(
        "was the duration of 'KERNEL LOG (dmesg)'", 1)[0]
    errors = [line for line in kernel.splitlines()
              if 'fastrpc_session_alloc failed' in line and 'ret -87' in line]
    assert errors
    report = dict(
        date='2026-11-09', timezone='Asia/Singapore', revision=options.tag,
        raw_capture_folder=str(options.capture.relative_to(PROJECT)), captures=captures,
        kernel_section_sha256=hashlib.sha256(kernel.encode()).hexdigest(),
        fastrpc_secure_session_failures_in_kernel=len(errors), first_failure=errors[0],
        failure_chain=[
            'The r33 rebuild omitted tp-autoconf.h for adsprpc-515 in two call sites',
            'CONFIG_QCOM_MEM_BUF_DEV was absent, selecting a static inline false ownership stub',
            'fastrpc_mmap_create classified ordinary DMA buffers as secure',
            'The sheng ADSP DT has no secure context bank, so secure session allocation returned EUSERS',
            'fastrpc_mmap_create translated EUSERS to ENOSR, causing adsprpcd and sscrpcd listener failure',
        ],
        before=dict(sha256=old.digest, missing_required_imports=missing),
        after=dict(sha256=sha(current), check=checks[1]), references=references,
        checks=dict(known_bad_r34_rejected=rejection, earlier_working_provider=checks[0],
                    rebuilt_provider=checks[1]),
        sensor_snapshot='Only Dynamic Sensor Manager; no accelerometer or gyroscope exposed',
        usb_snapshot='Wired ADB configured, UFP/device/sink, battery charging; no new USB fix applied',
        user_observations=['USB unavailable shortly after boot then recovers after tens of minutes',
            'Orientation sensor intermittent', 'Occasional speaker/charging-sound distortion',
            'Photo works; video recording fails'],
        limits=['Sensor recovery requires testing the rebuilt kernel on the device',
                'Speaker distortion and camera recording causality not yet verified',
                'Delayed USB recovery root cause remains unconfirmed'],
        hardware_result='pending', automatic_reboot_enabled=False,
    )
    built = PROJECT / ('reports/kernel618-' + options.tag + '-boot.json')
    layer_file = PROJECT / ('reports/kernel618-' + options.tag + '-layer.json')
    if built.is_file() and layer_file.is_file():
        boot = json.loads(built.read_text())
        layer = json.loads(layer_file.read_text())
        assert layer['checks']['abi_passed']
        report['candidate'] = dict(boot_sha256=boot['boot_sha256'],
            image_sha256=boot['image_sha256'],
            module_count=layer['archive']['module_count'],
            versioned_imports_checked=layer['checks']['versioned_imports_checked'],
            kernel_exports_unchanged=boot['kernel_exports_unchanged'],
            fastrpc_vendor_api_check=layer['fastrpc_vendor_api_check'],
            hardware_tested=False, flashed=False)
    target = PROJECT / 'reports/kernel618-fastrpc-config-source.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(report=str(target), before=report['before'],
                          after=report['after'], failures=len(errors)), indent=2))


if __name__ == '__main__':
    main()
