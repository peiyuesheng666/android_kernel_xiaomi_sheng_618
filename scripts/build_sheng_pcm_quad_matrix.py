#!/usr/bin/env python3
"""Build only PAL with a gated, valid stereo-to-quad channel-mixer payload."""
import difflib
import os
from pathlib import Path
import subprocess

rom = Path('/root/sheng-lineage/lineage-24.0')
workspace = Path(__file__).resolve().parents[1]
repo = rom / 'hardware/qcom-caf/sm8550/audio/pal'
changes = {}

path = repo / 'session/inc/PayloadBuilder.h'
before = path.read_text()
anchor = '    void payloadMFCMixerCoeff(uint8_t** payload, size_t* size,\n'
assert before.count(anchor) == 1
after = before.replace(anchor, '''    void payloadShengStereoQuadCoeff(uint8_t** payload, size_t* size,
                           uint32_t miid);
''' + anchor, 1)
changes[path] = (before, after)

path = repo / 'session/src/PayloadBuilder.cpp'
before = path.read_text()
anchor = 'void PayloadBuilder::payloadMFCConfig(uint8_t** payload, size_t* size,\n'
assert before.count(anchor) == 1
after = before.replace(anchor, '''void PayloadBuilder::payloadShengStereoQuadCoeff(uint8_t** payload, size_t* size,
        uint32_t miid)
{
    constexpr uint16_t inputChannels = 2;
    constexpr uint16_t outputChannels = 4;
    static_assert(sizeof(apm_module_param_data_t) == 16, "APM header ABI");
    static_assert(sizeof(param_id_chmixer_coeff_t) == 4, "mixer table header ABI");
    static_assert(sizeof(chmixer_coeff_t) == 4, "mixer channel header ABI");
    const size_t payloadSize = sizeof(apm_module_param_data_t) +
            sizeof(param_id_chmixer_coeff_t) + sizeof(chmixer_coeff_t) +
            sizeof(uint16_t) * (outputChannels + inputChannels +
                               outputChannels * inputChannels);
    const size_t padBytes = PAL_PADDING_8BYTE_ALIGN(payloadSize);
    *payload = nullptr;
    *size = 0;
    uint8_t* data = static_cast<uint8_t*>(calloc(1, payloadSize + padBytes));
    if (!data)
        return;
    auto* header = reinterpret_cast<apm_module_param_data_t*>(data);
    header->module_instance_id = miid;
    header->param_id = PARAM_ID_CHMIXER_COEFF;
    header->param_size = payloadSize - sizeof(*header);
    auto* tableHeader = reinterpret_cast<param_id_chmixer_coeff_t*>(data + sizeof(*header));
    tableHeader->num_coeff_tbls = 1;
    auto* table = reinterpret_cast<chmixer_coeff_t*>(data + sizeof(*header) + sizeof(*tableHeader));
    table->num_output_channels = outputChannels;
    table->num_input_channels = inputChannels;
    auto* channels = reinterpret_cast<uint16_t*>(data + sizeof(*header) +
                                               sizeof(*tableHeader) + sizeof(*table));
    // Keep the output channel IDs unique; mirror samples via coefficients.
    populateChannelMap(channels, outputChannels); // FL, FR, LB, RB
    channels += outputChannels;
    populateChannelMap(channels, inputChannels); // FL, FR
    channels += inputChannels;
    // SPF coefficients have OUTPUT rows and INPUT columns. On sheng the
    // physical left speakers use TDM slots 0/1 and right speakers use 2/3.
    // Keep both slots on each physical side on the same stereo input.
    // Verified with isolated left/right PCM tones; Q14 unity adds no gain.
    constexpr uint16_t coefficients[] = {0x4000, 0, 0x4000, 0,
                                        0, 0x4000, 0, 0x4000};
    memcpy(channels, coefficients, sizeof(coefficients));
    *payload = data;
    *size = payloadSize + padBytes;
}

''' + anchor, 1)
changes[path] = (before, after)

path = repo / 'session/src/Session.cpp'
before = path.read_text()
after = before.replace('#include <sstream>\n', '#include <sstream>\n#include <cutils/properties.h>\n', 1)
anchor = '''    } else {
        PAL_ERR(LOG_TAG, "getModuleInstanceId failed");
        if (sAttr.direction == (PAL_AUDIO_INPUT | PAL_AUDIO_OUTPUT))
            status = 0;
    }
'''
assert after.count(anchor) == 1
after = after.replace(anchor, '''        char deviceName[PROPERTY_VALUE_MAX] = {};
        property_get("ro.product.vendor.device", deviceName, "");
        if (property_get_bool("vendor.audio.sheng.stereo_quad_coeff", false) &&
            !strcmp(deviceName, "sheng") &&
            dAttr.id == PAL_DEVICE_OUT_SPEAKER &&
            !strcmp(intf, "TDM-LPAIF-RX-SECONDARY") &&
            sAttr.direction == PAL_AUDIO_OUTPUT &&
            isPalPCMFormat(sAttr.out_media_config.aud_fmt_id) &&
            sAttr.out_media_config.ch_info.channels == 2 &&
            mfcData.numChannel == 4) {
            builder->payloadShengStereoQuadCoeff(&payload, &payloadSize, miid);
            if (!payload || !payloadSize) {
                status = -ENOMEM;
                goto exit;
            }
            PAL_INFO(LOG_TAG, "sheng PCM stereo->quad mixer: miid=%x payload=%zu stream=%d",
                     miid, payloadSize, sAttr.type);
            status = updateCustomPayload(payload, payloadSize);
            freeCustomPayload(&payload, &payloadSize);
            if (status)
                goto exit;
        }
''' + anchor, 1)
changes[path] = (before, after)

patch = []
for path, (before, after) in changes.items():
    assert 'vendor.audio.sheng.stereo_quad_test' not in before
    assert 'payloadShengStereoQuadCoeff' not in before
    path.write_text(after)
    relative = path.relative_to(repo)
    patch.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                     fromfile=f'a/{relative}', tofile=f'b/{relative}'))
(workspace / 'patches/sheng-pcm-stereo-quad-coeff-diagnostic.patch').write_text(''.join(patch))
environment = dict(os.environ)
environment['JAVA_HOME'] = str(rom / 'prebuilts/jdk/jdk21/linux-x86')
environment['PATH'] = environment['JAVA_HOME'] + '/bin:' + environment['PATH']
log = Path('/root/sheng-lineage/logs/sheng-pcm-stereo-quad-coeff.log')
with log.open('w') as output:
    result = subprocess.run([
        str(rom / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-f', 'out/combined-lineage_sheng.ninja', '-j8',
        'out/target/product/sheng/vendor/lib64/libar-pal.so',
    ], cwd=rom, env=environment, stdout=output, stderr=subprocess.STDOUT)
print(log.read_text()[-3500:])
raise SystemExit(result.returncode)
