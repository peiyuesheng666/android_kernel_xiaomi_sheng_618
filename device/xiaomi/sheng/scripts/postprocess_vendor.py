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
    bp.write_text(text)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('vendor', type=Path)
    postprocess_vendor(parser.parse_args().vendor)
