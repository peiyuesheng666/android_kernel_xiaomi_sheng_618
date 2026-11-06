#!/usr/bin/env python3
"""Batch the real C90/export checks for installed external-module headers."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
out = rom / 'out/target/product/sheng/obj/KERNEL_OBJ'
clang = rom / 'prebuilts/clang/host/linux-x86/clang-r596125/bin/clang'
base = [str(clang), '-std=c90', '-Wall', '-Werror=implicit-function-declaration',
        '--target=aarch64-linux-gnu', '-I./usr/include', '-S', '-o', '/dev/null', '-x', 'c', '/dev/null']
control = 'usr/include/display/media/msm_sde_rotator.h'
before = subprocess.run(base + ['-include', control, '-include', control], cwd=out,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
assert before.returncode and "incomplete type 'struct timespec'" in before.stdout
headers = []
for header in (out / 'usr/include').rglob('*.h'):
    command = header.with_name('.' + header.name + '.cmd')
    if command.is_file() and 'sm8550-modules/' in command.read_text():
        headers.append(str(header.relative_to(out)))
assert headers


def check(header):
    compile_result = subprocess.run(base + ['-D_POSIX_C_SOURCE=200809L', '-include', header, '-include', header],
        cwd=out, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    export_result = subprocess.run(['perl', str(rom / 'kernel/xiaomi/sm8550/scripts/headers_check.pl'),
        'usr/include', 'arm64', header], cwd=out, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return {'header': header, 'passed': compile_result.returncode == export_result.returncode == 0,
            'diagnostics': compile_result.stdout + export_result.stdout}


with ThreadPoolExecutor(max_workers=24) as pool:
    results = list(pool.map(check, sorted(headers)))
report = {'vendor_headers_checked': len(results), 'all_passed': all(row['passed'] for row in results),
          'original_timespec_failure_reproduced': True, 'user_cflags': '-D_POSIX_C_SOURCE=200809L',
          'header_tests_disabled': False, 'results': results}
(work / 'reports/vendor-uapi-check.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'results'}, indent=2))
for row in results:
    if not row['passed']:
        print(json.dumps(row))
raise SystemExit(0 if report['all_passed'] else 1)
