#!/usr/bin/env python3
"""Wait for one build process and publish an atomic completion event, without tailing logs."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import threading
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


def identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] in ('Z', 'X'):
            return None
        return {'pid': pid, 'start_ticks': fields[19],
                'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (FileNotFoundError, ProcessLookupError):
        return None


def alive(record):
    return bool(record) and identity(record['pid']) == record


def write_event(directory, event):
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f'.build-event.{os.getpid()}.tmp'
    with temporary.open('w') as output:
        json.dump(event, output, indent=2)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(directory / 'build-event.json')


def phase(directory):
    file = directory / 'build-phase.txt'
    return file.read_text().strip() if file.is_file() else None


def run(directory, command, disk_path, minimum_free):
    event = {'schema': 1, 'run_id': uuid.uuid4().hex, 'state': 'running',
             'started_at': now(), 'supervisor': identity(os.getpid()), 'worker': None,
             'log': str(directory / 'build-lineage.log')}
    write_event(directory, event)
    session_log = directory / ('build-session-' + event['run_id'] + '.log')
    event['session_log'] = str(session_log)
    code = 1
    worker = None
    pending_signal = None
    stop_monitor = threading.Event()
    space_failures = []
    monitor = None

    def forward(number, frame):
        nonlocal pending_signal
        pending_signal = number
        if worker is not None and worker.poll() is None:
            try:
                os.killpg(worker.pid, number)
            except ProcessLookupError:
                pass

    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(number, forward)

    def watch_space():
        while not stop_monitor.is_set():
            free = shutil.disk_usage(disk_path).free
            if free < minimum_free:
                space_failures.append(f'{disk_path} free space {free} bytes is below {minimum_free} bytes')
                try:
                    os.killpg(worker.pid, signal.SIGTERM)
                    if not stop_monitor.wait(30) and worker.poll() is None:
                        os.killpg(worker.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                return
            stop_monitor.wait(30)
    try:
        with session_log.open('w') as output:
            # Preserve the flock FD in the worker, so a surviving build cannot
            # lose its exclusion lock if the supervisor is killed.
            try:
                os.fstat(9)
                inherited = (9,)
            except OSError:
                inherited = ()
            worker = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                      start_new_session=True, pass_fds=inherited)
            event['worker'] = identity(worker.pid)
            write_event(directory, event)
            if pending_signal:
                forward(pending_signal, None)
            if minimum_free:
                monitor = threading.Thread(target=watch_space, daemon=True)
                monitor.start()
            # Blocking wait: no build-log reads and no progress polling.
            code = worker.wait()
    except Exception as error:
        event['supervisor_error'] = repr(error)
        if worker is not None and worker.poll() is None:
            os.killpg(worker.pid, signal.SIGTERM)
            worker.wait()
    finally:
        stop_monitor.set()
        if monitor:
            monitor.join(timeout=1)
    if space_failures:
        event['failure_reason'] = space_failures[0]
        if code == 0:
            code = 75
    event.update(state='finished', finished_at=now(), returncode=code,
                 signal=-code if code < 0 else None, succeeded=code == 0,
                 phase=phase(directory))
    write_event(directory, event)
    print(json.dumps(event), flush=True)
    return code if code >= 0 else 128 - code


def probe(directory):
    file = directory / 'build-event.json'
    if not file.is_file():
        return {'state': 'not-started'}
    event = json.loads(file.read_text())
    if event['state'] == 'running':
        if alive(event.get('supervisor')) or alive(event.get('worker')):
            return event
        # SIGKILL of both processes, an OOM, or a WSL restart cannot run traps.
        # Detect disappearance at the next wake-up; never infer success.
        event.update(state='interrupted', finished_at=now(), succeeded=False,
                     returncode=None, phase=phase(directory),
                     reason='Neither recorded process is alive; exit code unavailable')
        write_event(directory, event)
    return event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'probe'))
    parser.add_argument('--state-dir', type=Path, default=Path('/root/sheng-lineage/logs'))
    parser.add_argument('--disk-path', type=Path, default=Path('/mnt/c'))
    parser.add_argument('--min-free-gib', type=float, default=0)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == '--':
        command = command[1:]
    if args.action == 'run':
        if not command:
            parser.error('run requires a command after --')
        return run(args.state_dir, command, args.disk_path, int(args.min_free_gib * 1024**3))
    print(json.dumps(probe(args.state_dir), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
