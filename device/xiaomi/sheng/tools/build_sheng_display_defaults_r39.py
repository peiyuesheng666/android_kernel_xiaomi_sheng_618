#!/usr/bin/env python3
"""Scoped builds of the two device overlays and missing-row refresh initializer."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--rom', type=Path, default=Path('/root/sheng-lineage/lineage-24.0'))
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert datetime.now(timezone.utc).timestamp()-datetime.fromisoformat(audit['date_utc']).timestamp()<7200
    device = args.workspace/'device/xiaomi/sheng'
    args.work.mkdir(exist_ok=False)
    rom, work = args.rom, args.work
    host = rom/'out/host/linux-x86'
    jdk = rom/'prebuilts/jdk/jdk21/linux-x86'
    sdk = rom/'prebuilts/sdk/37.0/public/android.jar'
    aapt = host/'bin/aapt2'
    signer = host/'framework/apksigner.jar'
    commands = []
    env = dict(os.environ, JAVA_HOME=str(jdk), LD_LIBRARY_PATH=str(host/'lib64'),
               LANG='C.UTF-8', LC_ALL='C.UTF-8')

    def run(command):
        result = subprocess.run(list(map(str, command)), cwd=work, capture_output=True, text=True, env=env)
        commands.append(dict(command=list(map(str,command)),returncode=result.returncode,
                             stdout=result.stdout,stderr=result.stderr))
        (work/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        if result.returncode: raise RuntimeError(result.stdout+result.stderr)
        return result.stdout+result.stderr

    def cert(apk):
        output = run([jdk/'bin/java','-jar',signer,'verify','--print-certs',apk])
        return re.search(r'certificate SHA-256 digest: ([0-9a-f]+)',output).group(1)

    def sign(unsigned, output, key):
        aligned = output.with_suffix('.aligned.apk')
        run([host/'bin/zipalign','-P','16','-f','4',unsigned,aligned])
        security = rom/'build/target/product/security'
        run([jdk/'bin/java','-jar',signer,'sign','--key',security/(key+'.pk8'),
             '--cert',security/(key+'.x509.pem'),'--out',output,aligned])
        run([host/'bin/zipalign','-c','-P','16','4',output])

    payload = {}
    product = rom/'out/target/product/sheng'
    for name, target in (('FrameworkResOverlaySheng','framework-res.apk'),
                         ('LineageResOverlaySheng','org.lineageos.platform-res.apk')):
        source = device/'overlay'/name
        compiled = work/(name+'.zip')
        unsigned = work/(name+'.unsigned.apk')
        output = work/(name+'.apk')
        run([aapt,'compile','--dir',source/'res','-o',compiled])
        run([aapt,'link','-I',sdk,'--manifest',source/'AndroidManifest.xml',
             '--min-sdk-version','37','--target-sdk-version','37','--auto-add-overlay',
             '--no-resource-deduping','--no-resource-removal','-o',unsigned,compiled])
        sign(unsigned,output,'testkey')
        old = product/'odm/overlay'/output.name
        assert cert(output)==cert(old), 'Overlay certificate changed'
        run([host/'bin/idmap2','create','--target-apk-path',product/'system/framework'/target,
             '--overlay-apk-path',output,'--idmap-path',work/(name+'.idmap'),
             '--policy','public','--policy','odm','--policy','signature'])
        resources = run([aapt,'dump','resources',output])
        (work/(name+'.resources.txt')).write_text(resources)
        payload['odm/overlay/'+output.name] = dict(path=str(output),sha256=sha(output))

    source = device/'interfaces/display/defaults'
    classes, dex = work/'classes', work/'dex'
    classes.mkdir(); dex.mkdir()
    run([jdk/'bin/javac','-source','8','-target','8','-encoding','UTF-8',
         '-bootclasspath',str(rom/'prebuilts/sdk/tools/core-lambda-stubs.jar')+':'+str(sdk),
         '-d',classes,*sorted((source/'src').rglob('*.java'))])
    jar = work/'classes.jar'
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(classes.rglob('*.class')): archive.write(path,path.relative_to(classes).as_posix())
    run([jdk/'bin/java','-cp',rom/'prebuilts/r8/r8.jar','com.android.tools.r8.D8',
         '--release','--min-api','33','--lib',sdk,'--output',dex,jar])
    manifest = work/'manifest.apk'
    run([aapt,'link','-I',sdk,'--manifest',source/'AndroidManifest.xml','-o',manifest])
    unsigned = work/'ShengDisplayDefaults.unsigned.apk'
    with zipfile.ZipFile(manifest) as inputs, zipfile.ZipFile(unsigned,'w',zipfile.ZIP_DEFLATED) as archive:
        for entry in inputs.infolist(): archive.writestr(entry,inputs.read(entry))
        for path in dex.glob('*.dex'): archive.write(path,path.name)
        archive.write(source/'LICENSE','assets/LICENSE')
    output = work/'ShengDisplayDefaults.apk'
    sign(unsigned,output,'platform')
    run([jdk/'bin/java','-jar',signer,'verify','--verbose',output])
    payload['system_ext/priv-app/ShengDisplayDefaults/ShengDisplayDefaults.apk'] = dict(path=str(output),sha256=sha(output))
    inputs = [*sorted(source.rglob('*')),*sorted((device/'overlay/FrameworkResOverlaySheng').rglob('*')),
              *sorted((device/'overlay/LineageResOverlaySheng').rglob('*')),device/'device.mk',Path(__file__)]
    receipt = dict(revision=39,scoped_build_passed=True,full_product_build_passed=False,
                   overlayable_policy_enforced=True,payload=payload,preaudit_sha256=sha(args.audit),
                   sources_sha256={str(p):sha(p) for p in inputs if p.is_file()},
                   commands_sha256=sha(work/'commands.json'),systemui_changed=False)
    (work/'build-review.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__': main()
