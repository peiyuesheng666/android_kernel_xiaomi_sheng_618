#!/usr/bin/env python3
"""Build a property-gated stereo-to-quad MFC diagnostic, without repacking."""
raise SystemExit('Obsolete failed diagnostic: duplicate channel IDs caused silence. Do not load this patch or library.')
import difflib
import os
from pathlib import Path
import subprocess

rom = Path('/root/sheng-lineage/lineage-24.0')
workspace = Path(__file__).resolve().parents[1]
repo = rom / 'hardware/qcom-caf/sm8550/audio/pal'
source = repo / 'session/src/Session.cpp'
text = source.read_text()
marker = 'vendor.audio.sheng.stereo_quad_test'
if marker not in text:
    before = text
    text = text.replace('#include <sstream>\n', '#include <sstream>\n#include <cutils/properties.h>\n', 1)
    anchor = '''        if (dAttr.id == PAL_DEVICE_OUT_AUX_DIGITAL ||
            dAttr.id == PAL_DEVICE_OUT_AUX_DIGITAL_1 ||
            dAttr.id == PAL_DEVICE_OUT_HDMI)
            mfcData.ch_info = &dAttr.config.ch_info;
'''
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '''
        // Diagnostic only: determine whether empty rear channels mute two
        // of sheng's four TDM slots when playing ordinary stereo content.
        struct pal_channel_info shengStereoQuad = {};
        char shengQuadTest[PROPERTY_VALUE_MAX] = {};
        property_get("vendor.audio.sheng.stereo_quad_test", shengQuadTest, "0");
        if (!strcmp(shengQuadTest, "1") && dAttr.id == PAL_DEVICE_OUT_SPEAKER &&
            sAttr.direction == PAL_AUDIO_OUTPUT &&
            sAttr.out_media_config.ch_info.channels == 2 &&
            mfcData.numChannel == 4) {
            shengStereoQuad.channels = 4;
            shengStereoQuad.ch_map[0] = PAL_CHMAP_CHANNEL_FL;
            shengStereoQuad.ch_map[1] = PAL_CHMAP_CHANNEL_FR;
            shengStereoQuad.ch_map[2] = PAL_CHMAP_CHANNEL_FL;
            shengStereoQuad.ch_map[3] = PAL_CHMAP_CHANNEL_FR;
            mfcData.ch_info = &shengStereoQuad;
            PAL_INFO(LOG_TAG, "sheng diagnostic stereo quad MFC: FL FR FL FR");
        }
''')
    source.write_text(text)
    (workspace / 'patches/sheng-stereo-quad-diagnostic.patch').write_text(''.join(
        difflib.unified_diff(before.splitlines(True), text.splitlines(True),
                             fromfile='a/session/src/Session.cpp',
                             tofile='b/session/src/Session.cpp')))
environment = dict(os.environ)
environment['JAVA_HOME'] = str(rom / 'prebuilts/jdk/jdk21/linux-x86')
environment['PATH'] = environment['JAVA_HOME'] + '/bin:' + environment['PATH']
log = Path('/root/sheng-lineage/logs/sheng-stereo-quad-diagnostic.log')
with log.open('w') as output:
    result = subprocess.run([
        str(rom / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-f', 'out/combined-lineage_sheng.ninja', '-j8',
        'out/target/product/sheng/vendor/lib64/libar-pal.so',
    ], cwd=rom, env=environment, stdout=output, stderr=subprocess.STDOUT)
print(log.read_text()[-5000:])
raise SystemExit(result.returncode)
