#!/usr/bin/env python3
"""Attach the device-owned GSL API provider to generated vendor modules."""
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
        bp.write_text(text.replace(needle, needle+properties))

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('vendor', type=Path)
    postprocess_vendor(parser.parse_args().vendor)
