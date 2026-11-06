#!/usr/bin/env python3
"""Prepare a separate offload package builder; retain the PCM r2 rollback files."""
from pathlib import Path
import os
import subprocess

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
pal = rom / 'hardware/qcom-caf/sm8550/audio/pal'
source = pal / 'session/src/SessionAlsaCompress.cpp'
text = source.read_text()
text = text.replace('vendor.audio.sheng.offload_master_unity_test',
                    'vendor.audio.sheng.offload_master_unity')
text = text.replace('''            {
            // Retain the encoded mono input, but request two decoded PCM
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
            }
''', '''            {
                // Keep the encoded mono input and request stereo decoded PCM
                // so it follows the verified stereo speaker graph.
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
            }
''')
text = text.replace('''                // HE-AACv2 parametric stereo is decoded to two channels even
                // when the compressed track's declared input is mono.
''', '''                // Match the decoded stereo output for mono MP3 and for
                // HE-AACv2 parametric stereo; retain the original stream attrs.
''')
source.write_text(text)
sources = workspace / 'device/xiaomi/sheng'
properties = sources / 'properties/vendor.prop'
keys = {'vendor.audio.sheng.offload_quad_coeff': 'true',
        'vendor.audio.sheng.offload_master_unity': 'true'}
lines = [line for line in properties.read_text().splitlines()
         if not any(line.startswith(key + '=') for key in keys)]
properties.write_text('\n'.join(lines) + '\n' +
                      '\n'.join(key + '=' + value for key, value in keys.items()) + '\n')
policy = sources / 'configs/audio/sku_kalama/audio_policy_configuration.xml'
text = policy.read_text()
old = 'sources="primary output,deep_buffer,direct_pcm,voip_rx,mmap_no_irq_out"'
new = 'sources="primary output,deep_buffer,direct_pcm,compressed_offload,voip_rx,mmap_no_irq_out"'
if old in text:
    assert text.count(old) == 1
    policy.write_text(text.replace(old, new, 1))
else:
    assert text.count(new) == 1
for relative in ('properties/vendor.prop', 'configs/audio/sku_kalama/audio_policy_configuration.xml'):
    (rom / 'device/xiaomi/sheng' / relative).write_bytes((sources / relative).read_bytes())
subprocess.run(['git', '-C', str(pal), 'diff', '--check'], check=True)
(workspace / 'patches/sheng-speaker-offload.patch').write_bytes(
    subprocess.run(['git', '-C', str(pal), 'diff', '--', 'session/inc/PayloadBuilder.h',
                    'session/src/PayloadBuilder.cpp', 'session/src/Session.cpp',
                    'session/src/SessionAlsaCompress.cpp'], check=True, capture_output=True).stdout)
environment = dict(os.environ)
environment['JAVA_HOME'] = str(rom / 'prebuilts/jdk/jdk21/linux-x86')
environment['PATH'] = environment['JAVA_HOME'] + '/bin:' + environment['PATH']
log = Path('/root/sheng-lineage/logs/sheng-offload-release.log')
with log.open('w') as output:
    result = subprocess.run([str(rom / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-f', 'out/combined-lineage_sheng.ninja', '-j8',
        'out/target/product/sheng/vendor/lib64/libar-pal.so'], cwd=rom,
        env=environment, stdout=output, stderr=subprocess.STDOUT)
print(log.read_text()[-1500:])
if result.returncode:
    raise SystemExit(result.returncode)
(workspace / 'artifacts/audio-diagnostics-sheng/libar-pal-offload-release.so').write_bytes(
    (rom / 'out/target/product/sheng/vendor/lib64/libar-pal.so').read_bytes())

# Reuse the existing verified EROFS/AVB machinery in a separate script with
# offload-specific inputs and assertions, leaving the PCM builder unchanged.
builder = (workspace / 'scripts/package_sheng_pcm_audio.py').read_text()
start = builder.index('# Correct the explanatory comment')
end = builder.index('effects = sources', start)
builder = builder[:start] + '''pal = rom / 'hardware/qcom-caf/sm8550/audio/pal'
tested_library = workspace / 'artifacts/audio-diagnostics-sheng/libar-pal-offload-release.so'
assert sha(tested_library) == args.tested_library_sha256
assert sha(product / 'vendor/lib64/libar-pal.so') == sha(tested_library)

''' + builder[end:]
replacements = {
    'Package the verified basic PCM speaker fix': 'Package the verified PCM and compressed-offload speaker fix',
    "parser.add_argument('--revision', type=int, default=2, choices=(2,))":
        "parser.add_argument('--revision', type=int, default=1, choices=(1,))\nparser.add_argument('--tested-library-sha256', required=True)",
    "base_dir = workspace / 'artifacts/system-audio-pcm-sheng-r1'":
        "base_dir = workspace / 'artifacts/system-audio-pcm-sheng-r2'",
    'artifacts/system-audio-pcm-sheng-r{args.revision}': 'artifacts/system-audio-offload-sheng-r{args.revision}',
    '/root/sheng-lineage/system-audio-pcm-r{args.revision}': '/root/sheng-lineage/system-audio-offload-r{args.revision}',
    "assert 'compressed_offload' not in speaker_sources and 'deep_buffer' in speaker_sources":
        "assert 'compressed_offload' in speaker_sources and 'deep_buffer' in speaker_sources",
    "    'etc/audio/sku_kalama/audio_effects.xml': effects,\n    'etc/audio_effects.xml': effects,\n": '',
    "keys = ('audio.deep_buffer.media', 'vendor.audio.sheng.stereo_quad_coeff')":
        "keys = ('audio.deep_buffer.media', 'vendor.audio.sheng.stereo_quad_coeff',\n        'vendor.audio.sheng.offload_quad_coeff', 'vendor.audio.sheng.offload_master_unity')",
    "'speaker_offload_excluded_by_policy': True": "'speaker_offload_enabled_by_policy': True,\n          'tested_pal_sha256': sha(tested_library), 'dolby_enabled': False",
    'reports/system-audio-pcm-r{args.revision}.json': 'reports/system-audio-offload-r{args.revision}.json',
}
for old, new in replacements.items():
    assert old in builder, old
    builder = builder.replace(old, new)
(workspace / 'scripts/package_sheng_offload_audio.py').write_text(builder)
print('Prepared separate offload release builder and combined PAL patch.')
