#!/usr/bin/env python3
"""Attach device-owned inputs to generated vendor modules, never public source."""
from pathlib import Path

def postprocess_vendor(vendor: Path):
    bp = vendor/'Android.bp'
    text = bp.read_text()
    needle = '    name: "libar-gsl",\n'
    properties = ('    header_libs: ["libsheng_gsl_headers"],\n'
                  '    export_header_lib_headers: ["libsheng_gsl_headers"],\n')
    assert text.count(needle) == 1
    if needle + properties not in text:
        assert 'libsheng_gsl_headers' not in text
        text = text.replace(needle, needle+properties)
    for name, source, replacement in (
        ('libdlbdsservice', 'proprietary/vendor/lib64/libdlbdsservice.so', ':sheng_dolby_dms_compat'),
        ('libhwdap', 'proprietary/vendor/lib64/soundfx/libhwdap.so', ':sheng_dolby_effect_compat'),
        ('libdlbpreg', 'proprietary/vendor/lib64/libdlbpreg.so', ':sheng_dolby_pregain_compat'),
        ('libdlbvol', 'proprietary/vendor/lib64/soundfx/libdlbvol.so', ':sheng_dolby_volume_compat'),
        ('c2.dolby.hevc.dec', 'proprietary/vendor/lib64/c2.dolby.hevc.dec.so', ':sheng_dolby_video_decoder_compat'),
        ('c2.dolby.hevc.sec.dec', 'proprietary/vendor/lib64/c2.dolby.hevc.sec.dec.so', ':sheng_dolby_video_secure_decoder_compat'),
    ):
        start = text.index('    name: "'+name+'",')
        end = text.index('\n}\n', start)+3
        section = text[start:end]
        if '"'+source+'"' in section:
            section = section.replace('"'+source+'"', '"'+replacement+'"')
            # Only the arm64 client has the isolated ABI. Leave any stock arm
            # client and its dependency list unchanged.
            arch = section.index('android_arm64:')
            section = section[:arch]+section[arch:].replace('"libstagefright_foundation"', '"libshgdolby_foundation"')
            text = text[:start]+section+text[end:]
        else:
            assert '"'+replacement+'"' in section and '"libshgdolby_foundation"' in section
    # Resize only the reviewed GraphicBuffer allocations in the generated
    # library outputs. The original module identities/dependencies stay intact.
    for name, source, replacement in (
        ('camera.xiaomi', 'odm/lib64/hw/camera.xiaomi.so', ':sheng_gb_camera_compat'),
        ('libcom.xiaomi.grallocutils', 'odm/lib64/libcom.xiaomi.grallocutils.so', ':sheng_gb_grallocutils_compat'),
        ('libcom.xiaomi.mawutils', 'odm/lib64/libcom.xiaomi.mawutils.so', ':sheng_gb_mawutils_compat'),
        ('libmis_plugin_vidhance', 'odm/lib64/libmis_plugin_vidhance.so', ':sheng_gb_vidhance_compat'),
        ('c2.dolby.hevc.enc', 'vendor/lib64/c2.dolby.hevc.enc.so', ':sheng_gb_dolby_encoder_compat'),
    ):
        start = text.index('    name: "' + name + '",')
        end = text.index('\n}\n', start) + 3
        section = text[start:end]
        original = '"proprietary/' + source + '"'
        if original in section:
            assert section.count(original) == 1
            section = section.replace(original, '"' + replacement + '"')
            text = text[:start] + section + text[end:]
        else:
            assert section.count('"' + replacement + '"') == 1
    # Keep one installer per original binary path. Source mains compile as
    # non-installable modules; the generated vendor prebuilts consume their ELF
    # outputs, preserving original init/module identities without Make conflicts.
    for name, replacement in (
        ('dolbycodec2', ':sheng-dolbycodec2'),
        ('vendor.dolby.media.c2@1.0-service', ':sheng-vendor.dolby.media.c2@1.0-service'),
    ):
        source = 'proprietary/vendor/bin/hw/' + name
        start = text.index('    name: "' + name + '",')
        end = text.index('\n}\n', start) + 3
        section = text[start:end]
        if '"' + source + '"' in section:
            section = section.replace('"' + source + '"', '"' + replacement + '"')
        else:
            assert section.count('"' + replacement + '"') == 1
        # The platform Codec2 defaults export these dependencies to the source
        # binary. Preserve ELF dependency checks in the prebuilt installer too.
        for dependency in ('libcodec2_hal_common', 'server_configurable_flags',
                           'libaconfig_storage_read_api_cc'):
            if '"' + dependency + '"' not in section:
                assert section.count('shared_libs: [') == 1
                section = section.replace('shared_libs: [',
                    'shared_libs: [\n                "' + dependency + '",')
        text = text[:start] + section + text[end:]
    bp.write_text(text)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('vendor', type=Path)
    postprocess_vendor(parser.parse_args().vendor)
