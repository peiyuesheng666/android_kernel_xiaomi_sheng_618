#!/usr/bin/env python3
"""Include each CHMIXER coefficient table's 4-byte ABI padding in param_size."""
from pathlib import Path
import difflib
import os
import subprocess

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
repo = rom / 'hardware/qcom-caf/sm8550/audio/pal'
source = repo / 'session/src/PayloadBuilder.cpp'
before = source.read_text()
old = '''    const size_t payloadSize = sizeof(apm_module_param_data_t) +
            sizeof(param_id_chmixer_coeff_t) + sizeof(chmixer_coeff_t) +
            sizeof(uint16_t) * (outputChannels + inputChannels +
                               outputChannels * inputChannels);
'''
new = '''    // SPF validates every coefficient table at 4-byte alignment. Include
    // that padding in param_size, separately from the outer 8-byte APM padding.
    const size_t tableBytes = sizeof(chmixer_coeff_t) +
            sizeof(uint16_t) * (outputChannels + inputChannels +
                               outputChannels * inputChannels);
    const size_t payloadSize = sizeof(apm_module_param_data_t) +
            sizeof(param_id_chmixer_coeff_t) + ((tableBytes + 3) & ~size_t(3));
'''
if old in before:
    assert before.count(old) == 1
    after = before.replace(old, new, 1)
    source.write_text(after)
    (workspace / 'patches/sheng-offload-mono-alignment.patch').write_text(
        ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
            fromfile='a/session/src/PayloadBuilder.cpp', tofile='b/session/src/PayloadBuilder.cpp')))
else:
    assert new in before
environment = dict(os.environ)
environment['JAVA_HOME'] = str(rom / 'prebuilts/jdk/jdk21/linux-x86')
environment['PATH'] = environment['JAVA_HOME'] + '/bin:' + environment['PATH']
log = Path('/root/sheng-lineage/logs/sheng-offload-mono-alignment.log')
with log.open('w') as output:
    result = subprocess.run([str(rom / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-f', 'out/combined-lineage_sheng.ninja', '-j8',
        'out/target/product/sheng/vendor/lib64/libar-pal.so'], cwd=rom,
        env=environment, stdout=output, stderr=subprocess.STDOUT)
print(log.read_text()[-1500:])
if result.returncode:
    raise SystemExit(result.returncode)
(workspace / 'artifacts/audio-diagnostics-sheng/libar-pal-offload-mono-aligned.so').write_bytes(
    (rom / 'out/target/product/sheng/vendor/lib64/libar-pal.so').read_bytes())
