#!/usr/bin/env python3
"""Test a nominal master gain before per-channel offload attenuation."""
from pathlib import Path
import difflib
import os
import subprocess

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
repo = rom / 'hardware/qcom-caf/sm8550/audio/pal'
source = repo / 'session/src/SessionAlsaCompress.cpp'
before = source.read_text()
marker = 'vendor.audio.sheng.offload_master_unity_test'
if marker not in before:
    after = before.replace('#include "media_fmt_api.h"\n',
                           '#include "media_fmt_api.h"\n#include <cutils/properties.h>\n', 1)
    anchor = '''            if (vdata->no_of_volpair == 2 && sAttr.out_media_config.ch_info.channels == 2) {
                builder->payloadMultichVolumemConfig(&alsaParamData, &alsaPayloadSize, miid, vdata);
'''
    assert after.count(anchor) == 1
    code = '''            char deviceName[PROPERTY_VALUE_MAX] = {};
            property_get("ro.product.vendor.device", deviceName, "");
            if (property_get_bool("vendor.audio.sheng.offload_master_unity_test", false) &&
                !strcmp(deviceName, "sheng") &&
                sAttr.type == PAL_STREAM_COMPRESSED &&
                sAttr.direction == PAL_AUDIO_OUTPUT &&
                sAttr.out_media_config.ch_info.channels == 2 &&
                !rxAifBackEnds.empty() &&
                rxAifBackEnds[0].second == "TDM-LPAIF-RX-SECONDARY") {
                auto* unity = static_cast<pal_volume_data*>(calloc(1,
                        sizeof(pal_volume_data) + sizeof(pal_channel_vol_kv)));
                if (!unity) { status = -ENOMEM; goto exit; }
                unity->no_of_volpair = 1;
                unity->volume_pair[0].channel_mask = 0x03;
                unity->volume_pair[0].vol = 1.0f;
                builder->payloadVolumeConfig(&alsaParamData, &alsaPayloadSize, miid, unity);
                free(unity);
                if (!alsaParamData || !alsaPayloadSize) { status = -ENOMEM; goto exit; }
                status = SessionAlsaUtils::setMixerParameter(mixer, device,
                        alsaParamData, alsaPayloadSize);
                freeCustomPayload(&alsaParamData, &alsaPayloadSize);
                PAL_INFO(LOG_TAG, "sheng offload nominal master gain: miid=%x status=%d", miid, status);
                if (status) goto exit;
            }

'''
    after = after.replace(anchor, code + anchor, 1)
    source.write_text(after)
    patch = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                    fromfile='a/session/src/SessionAlsaCompress.cpp',
                    tofile='b/session/src/SessionAlsaCompress.cpp'))
    (workspace / 'patches/sheng-offload-master-unity-diagnostic.patch').write_text(patch)
environment = dict(os.environ)
environment['JAVA_HOME'] = str(rom / 'prebuilts/jdk/jdk21/linux-x86')
environment['PATH'] = environment['JAVA_HOME'] + '/bin:' + environment['PATH']
log = Path('/root/sheng-lineage/logs/sheng-offload-master-unity.log')
with log.open('w') as output:
    result = subprocess.run([str(rom / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-f', 'out/combined-lineage_sheng.ninja', '-j8',
        'out/target/product/sheng/vendor/lib64/libar-pal.so'], cwd=rom,
        env=environment, stdout=output, stderr=subprocess.STDOUT)
print(log.read_text()[-1500:])
if result.returncode: raise SystemExit(result.returncode)
(workspace / 'artifacts/audio-diagnostics-sheng/libar-pal-offload-master-unity.so').write_bytes(
    (rom / 'out/target/product/sheng/vendor/lib64/libar-pal.so').read_bytes())
