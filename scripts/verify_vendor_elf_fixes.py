#!/usr/bin/env python3
"""Re-run all six real failed ELF checks against their actual providers."""
import json
from pathlib import Path
import shlex
import subprocess

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
logs = rom.parent / 'logs'
directory = rom.parent / 'out/verify-vendor-elf'
directory.mkdir(parents=True, exist_ok=True)
provider = directory / 'libsheng_audio_log_compat.so'
subprocess.run([str(rom / 'prebuilts/clang/host/linux-x86/clang-r596125/bin/clang'),
    '--target=aarch64-linux-android37', '-fuse-ld=lld', '-shared', '-fPIC', '-nostdlib',
    '-Wl,-soname,libsheng_audio_log_compat.so', '-o', str(provider),
    str(work / 'device/xiaomi/sheng/compat/AudioLogLevel.c')], check=True)
vendor = rom / 'out/target/product/sheng/vendor/lib64'
def compiled(relative, name):
    matches = list((rom / 'out/soong/.intermediates' / relative).glob('android_vendor_arm64*_shared/' + name))
    assert len(matches) == 1, (relative, matches)
    return matches[0]

nativewindow = compiled('frameworks/native/libs/nativewindow/libnativewindow', 'libnativewindow.so')
providers = {'libMiPhotoFilter.so': nativewindow,
             'libmorpho_ubwc.so': nativewindow,
             'libTrueSight.so': nativewindow,
             'libwrapper_dlengine.so': compiled('system/logging/liblog/liblog', 'liblog.so'),
             'libcrussp.so': provider,
             'c2.dolby.client.so': compiled('hardware/lineage/compat/libcodec2_shim', 'libcodec2_shim.so')}
lines = (logs / 'failures/45914d243d64486c928c6ec7d413dda2.log').read_text().splitlines()
results = []
for index, line in enumerate(lines):
    if not line.startswith('FAILED: ') or not line.endswith('.check_elf_file'):
        continue
    command = shlex.split(lines[index + 1], comments=True)
    command = command[:command.index('&&')]
    assert command[0] == 'out/host/linux-x86/bin/check_elf_file'
    input_file = Path(command[-1])
    assert input_file.parts[:3] == ('vendor', 'xiaomi', 'sheng') and input_file.name in providers
    extra = providers[input_file.name]
    assert extra.is_file(), str(extra)
    command[-1:-1] = ['--shared-lib', str(extra)]
    log = logs / ('verify-elf-' + input_file.name + '.log')
    with log.open('w') as output:
        code = subprocess.run(command, cwd=rom, stdout=output, stderr=subprocess.STDOUT).returncode
    results.append({'file': str(input_file), 'returncode': code, 'provider': str(extra), 'log': str(log)})
assert len(results) == 6
report = {'all_six_real_elf_checks_passed': all(row['returncode'] == 0 for row in results),
          'results': results, 'soong_integration': 'pending validation run', 'checks_disabled': False}
(work / 'reports/vendor-elf-fix-verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
raise SystemExit(0 if report['all_six_real_elf_checks_passed'] else 1)
