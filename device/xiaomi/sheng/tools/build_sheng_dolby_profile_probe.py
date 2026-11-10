#!/usr/bin/env python3
"""Compile a diagnostic against the same StockDms source as the product app."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    device = Path(__file__).resolve().parents[1]
    rom = Path('/root/sheng-lineage/lineage-24.0')
    args.work.mkdir(exist_ok=False)
    classes, dex = args.work/'classes', args.work/'dex'
    classes.mkdir(); dex.mkdir()
    java = rom/'prebuilts/jdk/jdk21/linux-x86/bin'
    sdk = rom/'prebuilts/sdk/37.0/public/android.jar'
    framework = rom/'out/soong/.intermediates/frameworks/base/framework-minus-apex/android_common/combined/framework.jar'
    sources = [device/'tools/ShengDolbyProfileProbe.java',
               device/'dolby/ShengDolby/src/org/lineageos/sheng/dolby/StockDms.java']
    env = dict(os.environ, LANG='C.UTF-8', LC_ALL='C.UTF-8')
    subprocess.run(list(map(str, [java/'javac', '-source', '8', '-target', '8',
        '-encoding', 'UTF-8', '-cp', str(framework)+':'+str(sdk), '-d', classes, *sources])),
        env=env, check=True)
    subprocess.run(list(map(str, [java/'java', '-cp', rom/'prebuilts/r8/r8.jar',
        'com.android.tools.r8.D8', '--lib', sdk, '--min-api', '35', '--output', dex,
        *classes.rglob('*.class')])), env=env, check=True)
    output = args.work/'sheng-dolby-profile-probe.jar'
    with zipfile.ZipFile(output, 'w') as archive:
        archive.write(dex/'classes.dex', 'classes.dex')
    receipt = dict(sources_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                   jar_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    (args.work/'build-review.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(output)


if __name__ == '__main__':
    main()
