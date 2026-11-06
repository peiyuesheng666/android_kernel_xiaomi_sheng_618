#!/usr/bin/env python3
"""Restore source GSL header exports on the stock GSL prebuilt for all clients."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--vendor-tree', type=Path, default=rom / 'vendor/xiaomi/sheng')
args = parser.parse_args()


def original(file):
    repository = Path(subprocess.check_output(['git', '-C', str(file.parent), 'rev-parse', '--show-toplevel'], text=True).strip())
    return subprocess.check_output(['git', '-C', str(repository), 'show',
                                   'HEAD:' + str(file.relative_to(repository))], text=True)


relative = 'hardware/qcom-caf/sm8550/audio/graphservices/gsl/Android.bp'
file = rom / relative
base = original(file)
addition = '''
// Keep the stock shared library while exporting its matching source API headers.
cc_library_headers {
    name: "libsheng_gsl_headers",
    vendor: true,
    export_include_dirs: [
        "api",
        "dls_client_api",
        "hw_rsc_api",
        "rtc_api",
    ],
}
'''
updated = base.rstrip() + '\n' + addition
assert file.read_text() in (base, updated), 'Unexpected GSL build changes'
if file.read_text() != updated:
    file.write_text(updated)
(work / 'patches/gsl-prebuilt-header-provider.patch').write_text(''.join(difflib.unified_diff(
    base.splitlines(True), updated.splitlines(True), fromfile='a/' + relative, tofile='b/' + relative)))

bp = args.vendor_tree / 'Android.bp'
text = bp.read_text()
needle = '    name: "libar-gsl",\n'
assert text.count(needle) == 1
properties = '    header_libs: ["libsheng_gsl_headers"],\n    export_header_lib_headers: ["libsheng_gsl_headers"],\n'
if needle + properties not in text:
    assert 'libsheng_gsl_headers' not in text
    bp.write_text(text.replace(needle, needle + properties))

# Remove the earlier consumer-only workaround now that every GSL client inherits
# the correct include directories from its dependency.
pal = rom / 'hardware/qcom-caf/sm8550/audio/pal/Android.bp'
pal_base = original(pal)
if pal.read_text() != pal_base:
    assert hashlib.sha256(pal.read_bytes()).hexdigest() == 'a0639b9321fa454c548618fd83b13cb98afee30895853243f52c729cabbc5325'
    pal.write_text(pal_base)
(work / 'patches/pal-gsl-includes.patch').unlink(missing_ok=True)
report = {'stock_gsl_binary_retained': True, 'header_provider': 'libsheng_gsl_headers',
          'source': relative, 'source_sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
          'vendor_bp': str(bp), 'vendor_bp_sha256': hashlib.sha256(bp.read_bytes()).hexdigest(),
          'exported_header_dependency_configured': True,
          'soong_build_verification': 'pending validation run', 'pal_consumer_workaround_removed': True}
(work / 'reports/gsl-header-export.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
