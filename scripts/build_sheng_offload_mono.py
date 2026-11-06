#!/usr/bin/env python3
"""Cover mono decoded output as well as the verified stereo output."""
from pathlib import Path
import difflib
import os
import subprocess

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
repo = rom / 'hardware/qcom-caf/sm8550/audio/pal'
changes = {}
path = repo / 'session/inc/PayloadBuilder.h'
before = path.read_text()
old = '''    void payloadShengStereoQuadCoeff(uint8_t** payload, size_t* size,
                           uint32_t miid);'''
new = old.replace('uint32_t miid);', 'uint32_t miid, uint16_t inputChannels = 2);')
assert before.count(old) == 1
changes[path] = (before, before.replace(old, new, 1))

path = repo / 'session/src/PayloadBuilder.cpp'
before = path.read_text()
old = '''void PayloadBuilder::payloadShengStereoQuadCoeff(uint8_t** payload, size_t* size,
        uint32_t miid)
{
    constexpr uint16_t inputChannels = 2;
'''
new = '''void PayloadBuilder::payloadShengStereoQuadCoeff(uint8_t** payload, size_t* size,
        uint32_t miid, uint16_t inputChannels)
{
    *payload = nullptr;
    *size = 0;
    if (inputChannels != 1 && inputChannels != 2)
        return;
'''
assert before.count(old) == 1
after = before.replace(old, new, 1)
old = '    memcpy(channels, coefficients, sizeof(coefficients));\n'
new = '''    if (inputChannels == 1) {
        // A decoded mono center channel feeds every physical speaker slot.
        for (uint16_t i = 0; i < outputChannels; ++i)
            channels[i] = 0x4000;
    } else {
        memcpy(channels, coefficients, sizeof(coefficients));
    }
'''
assert after.count(old) == 1
changes[path] = (before, after.replace(old, new, 1))

path = repo / 'session/src/Session.cpp'
before = path.read_text()
old = '''            (isPalPCMFormat(sAttr.out_media_config.aud_fmt_id) ||
             (sAttr.type == PAL_STREAM_COMPRESSED &&
              property_get_bool("vendor.audio.sheng.offload_quad_coeff", false))) &&
            sAttr.out_media_config.ch_info.channels == 2 &&
'''
new = '''            ((isPalPCMFormat(sAttr.out_media_config.aud_fmt_id) &&
              sAttr.out_media_config.ch_info.channels == 2) ||
             (sAttr.type == PAL_STREAM_COMPRESSED &&
              property_get_bool("vendor.audio.sheng.offload_quad_coeff", false) &&
              (sAttr.out_media_config.ch_info.channels == 1 ||
               sAttr.out_media_config.ch_info.channels == 2))) &&
'''
assert before.count(old) == 1
after = before.replace(old, new, 1)
old = '            builder->payloadShengStereoQuadCoeff(&payload, &payloadSize, miid);\n'
new = '''            builder->payloadShengStereoQuadCoeff(&payload, &payloadSize, miid,
                    sAttr.out_media_config.ch_info.channels);
'''
assert after.count(old) == 1
after = after.replace(old, new, 1)
old = '''            PAL_INFO(LOG_TAG, "sheng %s stereo->quad mixer: miid=%x payload=%zu stream=%d format=%d",
                     isPalPCMFormat(sAttr.out_media_config.aud_fmt_id) ? "PCM" : "offload",
                     miid, payloadSize, sAttr.type, sAttr.out_media_config.aud_fmt_id);
'''
new = '''            PAL_INFO(LOG_TAG, "sheng %s %uch->quad mixer: miid=%x payload=%zu stream=%d format=%d",
                     isPalPCMFormat(sAttr.out_media_config.aud_fmt_id) ? "PCM" : "offload",
                     sAttr.out_media_config.ch_info.channels,
                     miid, payloadSize, sAttr.type, sAttr.out_media_config.aud_fmt_id);
'''
assert after.count(old) == 1
changes[path] = (before, after.replace(old, new, 1))

path = repo / 'session/src/SessionAlsaCompress.cpp'
before = path.read_text()
old = '''                status = configureMFC(rm, sAttr, dAttr, compressDevIds,
                            rxAifBackEnds[i].second.data());
'''
new = '''                auto mfcAttributes = sAttr;
                // HE-AACv2 parametric stereo is decoded to two channels even
                // when the compressed track's declared input is mono.
                char deviceName[PROPERTY_VALUE_MAX] = {};
                property_get("ro.product.vendor.device", deviceName, "");
                if (!strcmp(deviceName, "sheng") &&
                    property_get_bool("vendor.audio.sheng.offload_quad_coeff", false) &&
                    dAttr.id == PAL_DEVICE_OUT_SPEAKER &&
                    rxAifBackEnds[i].second == "TDM-LPAIF-RX-SECONDARY" &&
                    SND_AUDIOCODEC_AAC == codec.id &&
                    codec.options.generic.reserved[0] == AACObjHE_PS &&
                    codec.ch_out == CHS_2) {
                    mfcAttributes.out_media_config.ch_info.channels = CHS_2;
                }
                status = configureMFC(rm, mfcAttributes, dAttr, compressDevIds,
                            rxAifBackEnds[i].second.data());
'''
assert before.count(old) == 1
changes[path] = (before, before.replace(old, new, 1))

patch = []
for path, (before, after) in changes.items():
    path.write_text(after)
    relative = path.relative_to(repo)
    patch.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                     fromfile=f'a/{relative}', tofile=f'b/{relative}'))
(workspace / 'patches/sheng-offload-mono-quad-diagnostic.patch').write_text(''.join(patch))
environment = dict(os.environ)
environment['JAVA_HOME'] = str(rom / 'prebuilts/jdk/jdk21/linux-x86')
environment['PATH'] = environment['JAVA_HOME'] + '/bin:' + environment['PATH']
log = Path('/root/sheng-lineage/logs/sheng-offload-mono-quad.log')
with log.open('w') as output:
    result = subprocess.run([str(rom / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-f', 'out/combined-lineage_sheng.ninja', '-j8',
        'out/target/product/sheng/vendor/lib64/libar-pal.so'], cwd=rom,
        env=environment, stdout=output, stderr=subprocess.STDOUT)
print(log.read_text()[-2000:])
if result.returncode: raise SystemExit(result.returncode)
(workspace / 'artifacts/audio-diagnostics-sheng/libar-pal-offload-mono-quad.so').write_bytes(
    (rom / 'out/target/product/sheng/vendor/lib64/libar-pal.so').read_bytes())
