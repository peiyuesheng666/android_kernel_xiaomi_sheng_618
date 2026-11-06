#!/usr/bin/env python3
"""Build a gated stereo decoder-output matrix diagnostic, retaining PCM routing."""
from pathlib import Path
import difflib
import os
import subprocess

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
repo = rom / 'hardware/qcom-caf/sm8550/audio/pal'
source = repo / 'session/src/Session.cpp'
before = source.read_text()
marker = 'vendor.audio.sheng.offload_quad_coeff'
if marker not in before:
    anchor = '            isPalPCMFormat(sAttr.out_media_config.aud_fmt_id) &&\n'
    assert before.count(anchor) == 1
    after = before.replace(anchor, '''            (isPalPCMFormat(sAttr.out_media_config.aud_fmt_id) ||
             (sAttr.type == PAL_STREAM_COMPRESSED &&
              property_get_bool("vendor.audio.sheng.offload_quad_coeff", false))) &&
''', 1)
    old_log = '''            PAL_INFO(LOG_TAG, "sheng PCM stereo->quad mixer: miid=%x payload=%zu stream=%d",
                     miid, payloadSize, sAttr.type);
'''
    new_log = '''            PAL_INFO(LOG_TAG, "sheng %s stereo->quad mixer: miid=%x payload=%zu stream=%d format=%d",
                     isPalPCMFormat(sAttr.out_media_config.aud_fmt_id) ? "PCM" : "offload",
                     miid, payloadSize, sAttr.type, sAttr.out_media_config.aud_fmt_id);
'''
    assert after.count(old_log) == 1
    after = after.replace(old_log, new_log, 1)
    source.write_text(after)
    patch = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                    fromfile='a/session/src/Session.cpp', tofile='b/session/src/Session.cpp'))
    (workspace / 'patches/sheng-offload-quad-coeff-diagnostic.patch').write_text(patch)

environment = dict(os.environ)
environment['JAVA_HOME'] = str(rom / 'prebuilts/jdk/jdk21/linux-x86')
environment['PATH'] = environment['JAVA_HOME'] + '/bin:' + environment['PATH']
log = Path('/root/sheng-lineage/logs/sheng-offload-quad-coeff.log')
with log.open('w') as output:
    result = subprocess.run([str(rom / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-f', 'out/combined-lineage_sheng.ninja', '-j8',
        'out/target/product/sheng/vendor/lib64/libar-pal.so'],
        cwd=rom, env=environment, stdout=output, stderr=subprocess.STDOUT)
print(log.read_text()[-1800:])
if result.returncode:
    raise SystemExit(result.returncode)
destination = workspace / 'artifacts/audio-diagnostics-sheng/libar-pal-offload-quad-coeff.so'
destination.write_bytes((rom / 'out/target/product/sheng/vendor/lib64/libar-pal.so').read_bytes())

# Temporary policy restores only the Speaker's existing offload route.
policy = (workspace / 'device/xiaomi/sheng/configs/audio/sku_kalama/audio_policy_configuration.xml').read_text()
old_route = '''                <route type="mix" sink="Speaker"
                       sources="primary output,deep_buffer,direct_pcm,voip_rx,mmap_no_irq_out"/>'''
new_route = old_route.replace('direct_pcm,voip_rx', 'direct_pcm,compressed_offload,voip_rx')
assert policy.count(old_route) == 1
(workspace / 'artifacts/audio-diagnostics-sheng/audio_policy_offload_test.xml').write_text(
    policy.replace(old_route, new_route, 1))
print('Built PAL offload diagnostic and temporary Speaker policy.')
