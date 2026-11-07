#!/usr/bin/env python3
"""Compile the offscreen video diagnostic; never deploy or run it on a device."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    assert DEVICE == ROM / 'device/xiaomi/sheng'
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    classes = work / 'classes'
    classes.mkdir()
    sdk = ROM / 'prebuilts/sdk/current/public/android.jar'
    d8 = ROM / 'out/host/linux-x86/framework/d8.jar'
    java = ROM / 'prebuilts/jdk/jdk21/linux-x86/bin'
    source = DEVICE / 'tools/ShengVideoDecodeProbe.java'
    compile_command = [str(java / 'javac'), '-J-Xmx256m', '-source', '8', '-target', '8',
                       '-cp', str(sdk), '-d', str(classes), str(source)]
    subprocess.run(compile_command, check=True)
    jar = work / 'sheng-video-decode-probe.jar'
    dex_command = [str(java / 'java'), '-Xmx512m', '-cp', str(d8),
                   'com.android.tools.r8.D8', '--min-api', '34', '--lib', str(sdk),
                   '--output', str(jar), *map(str, sorted(classes.glob('*.class')))]
    subprocess.run(dex_command, check=True)
    report = dict(source_sha256=sha(source), sdk_sha256=sha(sdk), d8_sha256=sha(d8),
                  commands=[compile_command, dex_command], jar_sha256=sha(jar),
                  build_passed=True, runtime_verified=False, fixture_validated=False,
                  camera_used=False, displayed_or_saved_decoded_frames=False)
    (work / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
