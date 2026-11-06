#!/usr/bin/env python3
"""Request stereo decoder output for mono MP3 on sheng's TDM speaker route."""
from pathlib import Path
import difflib
import os
import subprocess

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
repo = rom / 'hardware/qcom-caf/sm8550/audio/pal'
source = repo / 'session/src/SessionAlsaCompress.cpp'
before = source.read_text()
marker = 'sheng mono MP3 stereo decoder output'
if marker not in before:
    anchor = '            compress_config.fragment_size = out_buf_size;\n'
    code = '''            // Retain the encoded mono input, but request two decoded PCM
            // channels so it follows the verified stereo speaker graph.
            char shengDeviceName[PROPERTY_VALUE_MAX] = {};
            property_get("ro.product.vendor.device", shengDeviceName, "");
            if (!strcmp(shengDeviceName, "sheng") &&
                property_get_bool("vendor.audio.sheng.offload_quad_coeff", false) &&
                codec.id == SND_AUDIOCODEC_MP3 && codec.ch_in == 1 &&
                !rxAifBackEnds.empty() &&
                rxAifBackEnds[0].second == "TDM-LPAIF-RX-SECONDARY") {
                codec.ch_out = CHS_2;
                PAL_INFO(LOG_TAG, "sheng mono MP3 stereo decoder output");
            }
'''
    assert before.count(anchor) == 1
    after = before.replace(anchor, code + anchor, 1)
    old = '''                    SND_AUDIOCODEC_AAC == codec.id &&
                    codec.options.generic.reserved[0] == AACObjHE_PS &&
                    codec.ch_out == CHS_2) {'''
    new = '''                    codec.ch_out == CHS_2 &&
                    ((SND_AUDIOCODEC_AAC == codec.id &&
                      codec.options.generic.reserved[0] == AACObjHE_PS) ||
                     (SND_AUDIOCODEC_MP3 == codec.id && codec.ch_in == 1))) {'''
    assert after.count(old) == 1
    after = after.replace(old, new, 1)
    source.write_text(after)
    (workspace / 'patches/sheng-offload-mono-stereo-output-diagnostic.patch').write_text(
        ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
            fromfile='a/session/src/SessionAlsaCompress.cpp', tofile='b/session/src/SessionAlsaCompress.cpp')))
current = source.read_text()
scope_start = '            // Retain the encoded mono input, but request two decoded PCM\n'
if scope_start in current:
    current = current.replace(scope_start, '            {\n' + scope_start, 1)
    scope_end = '''                PAL_INFO(LOG_TAG, "sheng mono MP3 stereo decoder output");
            }
            compress_config.fragment_size'''
    assert current.count(scope_end) == 1
    current = current.replace(scope_end, scope_end.replace(
        '            compress_config.fragment_size', '            }\n            compress_config.fragment_size'), 1)
    source.write_text(current)
environment = dict(os.environ)
environment['JAVA_HOME'] = str(rom / 'prebuilts/jdk/jdk21/linux-x86')
environment['PATH'] = environment['JAVA_HOME'] + '/bin:' + environment['PATH']
log = Path('/root/sheng-lineage/logs/sheng-offload-mono-stereo-output.log')
with log.open('w') as output:
    result = subprocess.run([str(rom / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-f', 'out/combined-lineage_sheng.ninja', '-j8',
        'out/target/product/sheng/vendor/lib64/libar-pal.so'], cwd=rom,
        env=environment, stdout=output, stderr=subprocess.STDOUT)
print(log.read_text()[-1500:])
if result.returncode:
    raise SystemExit(result.returncode)
(workspace / 'artifacts/audio-diagnostics-sheng/libar-pal-offload-mono-stereo-output.so').write_bytes(
    (rom / 'out/target/product/sheng/vendor/lib64/libar-pal.so').read_bytes())
