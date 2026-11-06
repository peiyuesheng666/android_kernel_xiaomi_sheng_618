#!/usr/bin/env python3
"""Trace the stock Dolby GEF request routing without changing its payloads."""
from pathlib import Path
import difflib
import os
import subprocess

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
repo = rom / 'hardware/qcom-caf/sm8550/audio/pal'
source = repo / 'Pal.cpp'
before = source.read_text()
if 'sheng GEF write' not in before:
    after = '#include <cutils/properties.h>\n' + before
    anchor = '''        if (GEF_PARAM_WRITE == dir) {
            status = rm->setParameter(param_id, param_payload, payload_size,
'''
    code = '''        if (GEF_PARAM_WRITE == dir) {
            if (param_id == PAL_PARAM_ID_UIEFFECT && param_payload &&
                payload_size >= sizeof(effect_pal_payload_t) &&
                property_get_bool("vendor.audio.sheng.dolby_trace", false)) {
                const auto *effect = static_cast<const effect_pal_payload_t*>(param_payload);
                PAL_INFO(LOG_TAG, "sheng GEF write: device=%d stream=%d tag=%x tkv=%d bytes=%zu payload=%u",
                         pal_device_id, pal_stream_type, effect->tag,
                         effect->isTKV, payload_size, effect->payloadSize);
            }
            status = rm->setParameter(param_id, param_payload, payload_size,
'''
    assert after.count(anchor) == 1
    after = after.replace(anchor, code, 1)
    source.write_text(after)
    (workspace / 'patches/sheng-dolby-gef-trace-diagnostic.patch').write_text(
        ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
            fromfile='a/Pal.cpp', tofile='b/Pal.cpp')))
environment = dict(os.environ)
environment['JAVA_HOME'] = str(rom / 'prebuilts/jdk/jdk21/linux-x86')
environment['PATH'] = environment['JAVA_HOME'] + '/bin:' + environment['PATH']
log = Path('/root/sheng-lineage/logs/sheng-dolby-gef-trace.log')
with log.open('w') as output:
    result = subprocess.run([str(rom / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-f', 'out/combined-lineage_sheng.ninja', '-j8',
        'out/target/product/sheng/vendor/lib64/libar-pal.so'], cwd=rom,
        env=environment, stdout=output, stderr=subprocess.STDOUT)
print(log.read_text()[-1500:])
if result.returncode:
    raise SystemExit(result.returncode)
(workspace / 'artifacts/audio-diagnostics-sheng/libar-pal-dolby-gef-trace.so').write_bytes(
    (rom / 'out/target/product/sheng/vendor/lib64/libar-pal.so').read_bytes())
