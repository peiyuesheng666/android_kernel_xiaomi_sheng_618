#!/usr/bin/env python3
"""Exercise completion, process signals, and disappearance with disposable commands."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

TOOL = Path(__file__).with_name('build_events.py')


class BuildEventsTest(unittest.TestCase):
    def command(self, directory, code):
        return [sys.executable, str(TOOL), '--state-dir', directory, 'run', '--',
                sys.executable, '-c', code]

    def test_success_failure_and_worker_sigkill(self):
        for script, expected, succeeded in (
            ('pass', 0, True), ('raise SystemExit(7)', 7, False),
            ('import os,signal; os.kill(os.getpid(),signal.SIGKILL)', 137, False),
        ):
            with self.subTest(script=script), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run(self.command(directory, script), capture_output=True, text=True)
                event = json.loads((Path(directory) / 'build-event.json').read_text())
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(event['state'], 'finished')
                self.assertEqual(event['succeeded'], succeeded)

    def test_disappeared_processes_are_interrupted_not_successful(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.Popen(self.command(directory, 'import time; time.sleep(60)'),
                                       stdout=subprocess.DEVNULL)
            worker_pid = None
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    file = Path(directory) / 'build-event.json'
                    if file.exists():
                        event = json.loads(file.read_text())
                        if event.get('worker'):
                            worker_pid = event['worker']['pid']
                            break
                    time.sleep(0.02)
                self.assertIsNotNone(worker_pid)
                process.kill()
                process.wait(timeout=5)
                os.killpg(worker_pid, signal.SIGKILL)
                time.sleep(0.1)
                result = subprocess.run([sys.executable, str(TOOL), '--state-dir', directory, 'probe'],
                                        capture_output=True, text=True, check=True)
                event = json.loads(result.stdout)
                self.assertEqual(event['state'], 'interrupted')
                self.assertFalse(event['succeeded'])
                self.assertIsNone(event['returncode'])
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_disk_floor_terminates_the_worker_and_records_the_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            command = self.command(directory, 'import time; time.sleep(60)')
            command[4:4] = ['--disk-path', directory, '--min-free-gib', '1000000000']
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            event = json.loads((Path(directory) / 'build-event.json').read_text())
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(event['succeeded'])
            self.assertIn('free space', event['failure_reason'])


if __name__ == '__main__':
    unittest.main()
