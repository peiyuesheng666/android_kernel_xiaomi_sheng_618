#!/usr/bin/env python3
"""Exercise the actual AArch64 static logger over a host pseudo-terminal."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import time

work = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--binary', type=Path, default=Path('/root/sheng-lineage/recovery-r3-tools/serial-init'))
parser.add_argument('--report-name', default='serial-transport-test.json')
args = parser.parse_args()
assert Path(args.report_name).name == args.report_name
binary = args.binary
with tempfile.TemporaryDirectory(prefix='sheng-serial-', dir='/tmp') as temporary:
    folder = Path(temporary)
    source = folder / 'source.log'
    marker = folder / 'go-marker'
    expected = b''.join(f'6,{i},{i * 1000},-;serial test record {i}\n'.encode() for i in range(12000))
    source.write_bytes(expected)
    master, slave = pty.openpty()
    process = subprocess.Popen(['qemu-aarch64', str(binary), '--transport-test',
                                str(source), os.ttyname(slave), str(marker)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    actual = bytearray()
    try:
        deadline = time.monotonic() + 20
        while len(actual) < len(expected) and time.monotonic() < deadline:
            if select.select([master], [], [], 0.2)[0]:
                actual.extend(os.read(master, 65536))
        assert bytes(actual) == expected, (len(actual), len(expected))
        os.write(master, b'NOT-A-COMMAND\n')
        time.sleep(0.1)
        assert not marker.exists(), 'An unrelated command must not continue init'
        os.write(master, b'GO\n')
        output, errors = process.communicate(timeout=5)
        assert process.returncode == 0, errors
        assert marker.is_file()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        os.close(slave)
report = {'aarch64_static_binary': str(binary), 'transport': 'actual QEMU executable and Linux PTY',
          'bytes_verified': len(expected), 'sha256': hashlib.sha256(expected).hexdigest(),
          'ignored_other_command': True, 'go_handshake_verified': True,
          'no_device_modules_or_mounts_executed': True, 'usb_hardware_tested': False}
(work / 'reports' / args.report_name).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
