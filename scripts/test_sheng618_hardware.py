#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""One bounded boot_a test: flash, await automatic Fastboot, temporary Recovery, read log.

Run under WSL Python 3.11; uses the workspace Windows platform-tools over USB.
Never retries a flash or loops back to boot the failing kernel. Stock images are read-only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from read_sheng618_disklog import decode

ROOT = Path(__file__).resolve().parents[1]
SERIAL = 'ca10ede3'
RECOVERY = ROOT / 'artifacts/recovery-sheng-lineage-24.0-r13-native-source-fast-touch/lineage-24.0-sheng-recovery-r13-native-source-fast-touch.img'
RECOVERY_SHA = '738556589abb2c35047879f14cfed63a05a6ed25c7c418a0209709622312376f'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def win(path):
    return subprocess.run(['wslpath', '-w', str(path.resolve())], check=True,
                          capture_output=True, text=True, timeout=5).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--readback-only', action='store_true', help='Recover a prior interrupted test without reflashing')
    options = parser.parse_args()
    assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}', options.revision)
    tag = options.revision
    delivery = ROOT / ('artifacts/sheng-6.18-' + tag)
    build = json.loads((delivery / 'build-result.json').read_text())
    assert build['revision'] == tag and build['test_timeout_seconds'] in (180, 600)
    test_timeout = build['test_timeout_seconds']
    assert sha(delivery / 'boot.img') == build['boot_sha256']
    assert sha(RECOVERY) == RECOVERY_SHA
    folder = ROOT / ('reports/device/kernel618-' + tag)
    folder.mkdir(parents=True, exist_ok=True)
    assert not (folder / 'region-after.bin').exists(), 'Preserve previous readback'
    if not options.readback_only:
        assert not (folder / 'flash.txt').exists(), 'Already flashed; use --readback-only'
    receipt = dict(revision=tag, serial=SERIAL, boot_sha256=build['boot_sha256'],
                   image_sha256=build['image_sha256'], test_timeout_seconds=test_timeout,
                   writes=['boot_a'], temporary_recovery_sha256=RECOVERY_SHA,
                   original_boot_backed_up=False, events=[])
    report = ROOT / ('reports/kernel618-' + tag + '-automation.json')
    transcript = folder / ('readback-control.txt' if options.readback_only else 'control.txt')

    def record(event, **data):
        item = dict(event=event, wall_time=time.strftime('%Y-%m-%dT%H:%M:%S%z'), **data)
        receipt['events'].append(item)
        report.write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(item), flush=True)

    def call(tool, *args, timeout=15, check=True, quiet=False):
        result = subprocess.run([str(ROOT / ('tools/platform-tools/' + tool + '.exe')),
                                 '-s', SERIAL, *map(str, args)],
                                capture_output=True, text=True, timeout=timeout)
        output = result.stdout + result.stderr
        if not quiet:
            with transcript.open('a') as stream:
                stream.write(f'[{tool} {" ".join(map(str, args))}] rc={result.returncode}\n{output}\n')
        if check and result.returncode:
            raise RuntimeError(f'{tool} failed ({result.returncode}): {output}')
        return output

    def fastboot_present():
        text = call('fastboot', 'devices', quiet=True, check=False, timeout=5)
        return bool(re.search(r'^' + SERIAL + r'\s+fastboot\s*$', text, re.M))

    def verify_fastboot():
        assert re.search(r'product:\s*sheng\b', call('fastboot', 'getvar', 'product'))
        assert re.search(r'current-slot:\s*a\b', call('fastboot', 'getvar', 'current-slot'))
        assert re.search(r'unlocked:\s*yes\b', call('fastboot', 'getvar', 'unlocked'))
        assert re.search(r'is-userspace:\s*no\b', call('fastboot', 'getvar', 'is-userspace'))

    def wait_fastboot(seconds, monitor_adb=False):
        deadline, next_notice, next_adb = time.monotonic() + seconds, 0, 0
        next_capture = 0
        while time.monotonic() < deadline:
            if fastboot_present():
                return
            now = time.monotonic()
            if monitor_adb and now >= next_adb:
                next_adb = now + 10
                devices = call('adb', 'devices', check=False, quiet=True, timeout=5)
                if re.search(r'^' + SERIAL + r'\s+device\s*$', devices, re.M):
                    release = call('adb', 'shell', 'uname -r', check=False, timeout=5)
                    if release.strip().startswith('6.18.'):
                        if not receipt.get('candidate_adb_connected'):
                            receipt['candidate_adb_connected'] = True
                            receipt['disable_test_mode_next_revision'] = True
                            record('candidate_adb_connected', kernel=release.strip())
                        if now >= next_capture:
                            next_capture = now + 60
                            stamp = str(round(now))
                            for name, command in (
                                ('properties', 'getprop'),
                                ('dmesg', 'dmesg'),
                                ('logcat', 'logcat -b all -d -t 2500'),
                                ('usb', 'cat /proc/uptime; ls -l /sys/class/udc; '
                                 'cat /sys/kernel/debug/devices_deferred; '
                                 'cat /sys/class/drm/card*-DSI-*/status; '
                                 'cat /sys/class/drm/card*-DSI-*/modes'),
                            ):
                                output = call('adb', 'shell', command, check=False, quiet=True, timeout=20)
                                (folder / f'adb-{stamp}-{name}.txt').write_text(output)
                            record('candidate_diagnostics_saved', prefix='adb-' + stamp)
            if now >= next_notice:
                next_notice = now + 30
                record('waiting_for_fastboot', seconds_remaining=round(deadline - now))
            time.sleep(1)
        raise TimeoutError('Automatic Fastboot not received in bounded test window')

    try:
        if not fastboot_present():
            state = call('adb', 'get-state', check=False).strip()
            assert state in ('recovery', 'device'), state
            assert call('adb', 'shell', 'getprop ro.product.device').strip() == 'sheng'
            call('adb', 'reboot', 'bootloader')
            wait_fastboot(60)
        verify_fastboot()
        if not options.readback_only:
            output = call('fastboot', 'flash', 'boot_a', win(delivery / 'boot.img'), timeout=180)
            assert 'OKAY' in output and 'FAILED' not in output
            (folder / 'flash.txt').write_text(output)
            record('boot_a_flashed')
            call('fastboot', 'reboot')
            start = time.monotonic()
            # Require USB departure, so the initial bootloader is never mistaken for a return.
            departure_deadline = start + 15
            while fastboot_present():
                if time.monotonic() >= departure_deadline:
                    raise TimeoutError('USB never departed Fastboot after reboot')
                time.sleep(0.5)
            record('candidate_started')
            wait_fastboot(test_timeout + 55, monitor_adb=True)
            receipt['automatic_fastboot_return'] = True
            record('automatic_fastboot_received', elapsed_seconds=round(time.monotonic() - start, 2))
            verify_fastboot()
        call('fastboot', 'boot', win(RECOVERY), timeout=90)
        record('temporary_recovery_started')
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            state = call('adb', 'get-state', check=False, quiet=True, timeout=5).strip()
            if state == 'recovery':
                break
            time.sleep(1)
        else:
            raise TimeoutError('Recovery ADB missing')
        assert call('adb', 'shell', 'uname -r').strip() == '5.15.220-gf9ca2b71f672'
        assert call('adb', 'shell', 'getprop ro.product.device').strip() == 'sheng'
        call('adb', 'shell', 'dd if=/dev/block/by-name/rawdump of=/tmp/sheng-bootlog.bin bs=1048576 skip=288 count=2', timeout=30)
        call('adb', 'pull', '/tmp/sheng-bootlog.bin', win(folder / 'region-after.bin'), timeout=30)
        raw = (folder / 'region-after.bin').read_bytes()
        assert len(raw) == 2 * 1024**2
        logs = decode(raw)
        if build.get('periodic_log_identity'):
            current = [s for s in logs if
                       'sheng_bootlog: identity revision=' + tag + ' run=' + s['run'] + '\n' in s['text']]
        else:
            current = [s for s in logs if 'sheng_test=' + tag + ' ' in s['text']]
        assert current, 'No CRC-valid snapshot from the requested revision; preserve for diagnosis'
        assert len({s['run'] for s in current}) == 1
        for log in current:
            (folder / f"bootlog-{log['run']}-{log['sequence']}.txt").write_text(log['text'])
        latest = max(current, key=lambda s: s['sequence'])
        receipt.update(raw_sha256=hashlib.sha256(raw).hexdigest(), run=latest['run'],
                       valid_snapshots=[{k: s[k] for k in ('sequence', 'uptime_ms')} for s in current],
                       log_readback_succeeded=True,
                       latest_log=str((folder / f"bootlog-{latest['run']}-{latest['sequence']}.txt").relative_to(ROOT)))
        record('log_readback_complete', run=latest['run'], uptime_ms=latest['uptime_ms'])
        call('adb', 'reboot', 'bootloader')
        wait_fastboot(60)
        verify_fastboot()
        record('finished_in_fastboot')
    except Exception as error:
        record('failed', error=str(error))
        raise


if __name__ == '__main__':
    main()
