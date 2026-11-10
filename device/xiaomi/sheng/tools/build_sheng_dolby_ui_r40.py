#!/usr/bin/env python3
"""Compile source-owned Monet Dolby UI and API 1 bootstrap without platform edits."""
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--rom',type=Path,default=Path('/root/sheng-lineage/lineage-24.0'))
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--preaudit',type=Path,required=True)
    parser.add_argument('--revision',type=int,default=40)
    parser.add_argument('--normal-build-log',type=Path)
    args=parser.parse_args()
    audit=json.loads(args.preaudit.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert datetime.now(timezone.utc).timestamp()-datetime.fromisoformat(audit['date_utc']).timestamp()<7200
    source=args.workspace/'device/xiaomi/sheng/dolby/ShengDolby'
    args.work.mkdir(exist_ok=False)
    work,rom=args.work,args.rom
    host=rom/'out/host/linux-x86'; jdk=rom/'prebuilts/jdk/jdk21/linux-x86'
    sdk=rom/'prebuilts/sdk/37.0/public/android.jar'
    old_sdk=rom/'prebuilts/sdk/1/public/android.jar'
    framework=rom/'out/soong/.intermediates/frameworks/base/framework-minus-apex/android_common/combined/framework.jar'
    sdk_audit={}
    for jar in (sdk,old_sdk):
        relative=jar.relative_to(rom/'prebuilts/sdk').as_posix()
        expected=subprocess.check_output(['git','-C',rom/'prebuilts/sdk','rev-parse','HEAD:'+relative],text=True).strip()
        raw=jar.read_bytes()
        actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        assert actual==expected,jar
        sdk_audit[relative]=dict(expected_blob=expected,actual_blob=actual,sha256=sha(jar))
    commands=[]
    env=dict(os.environ,LANG='C.UTF-8',LC_ALL='C.UTF-8',JAVA_HOME=str(jdk),LD_LIBRARY_PATH=str(host/'lib64'))
    def run(command):
        result=subprocess.run(list(map(str,command)),cwd=work,env=env,capture_output=True,text=True)
        commands.append(dict(command=list(map(str,command)),returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
        (work/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        return result.stdout+result.stderr
    generated,classes,dex,legacy=[work/x for x in ('generated','classes','dex','api1-bootstrap')]
    for folder in (generated,classes,dex,legacy):folder.mkdir()
    aapt=host/'bin/aapt2'; compiled=work/'resources.zip'; resources=work/'resources.apk'
    run([aapt,'compile','--dir',source/'res','-o',compiled])
    run([aapt,'link','-I',sdk,'--manifest',source/'AndroidManifest.xml','--min-sdk-version','1',
         '--target-sdk-version','37','--java',generated,'-o',resources,compiled])
    bootstraps=[source/'src/org/lineageos/sheng/dolby'/name for name in ('CompatibilityApplication.java','CompatibilityActivity.java')]
    run([jdk/'bin/javac','-source','8','-target','8','-encoding','UTF-8','-classpath',old_sdk,
         '-d',legacy,*bootstraps,*generated.rglob('*.java')])
    run([jdk/'bin/javac','-source','8','-target','8','-encoding','UTF-8','-classpath',str(framework)+':'+str(sdk),
         '-d',classes,*source.rglob('*.java'),*generated.rglob('*.java')])
    jar=work/'classes.jar'
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in classes.rglob('*.class'):archive.write(path,path.relative_to(classes).as_posix())
    run([jdk/'bin/java','-cp',rom/'prebuilts/r8/r8.jar','com.android.tools.r8.D8','--release',
         '--min-api','1','--lib',sdk,'--output',dex,jar])
    unsigned=work/'ShengDolby.unsigned.apk'
    with zipfile.ZipFile(resources) as inputs,zipfile.ZipFile(unsigned,'w',zipfile.ZIP_DEFLATED) as archive:
        for entry in inputs.infolist():archive.writestr(entry,inputs.read(entry))
        for path in dex.glob('*.dex'):
            assert path.read_bytes()[:8]==b'dex\n035\0'
            archive.write(path,path.name)
    aligned=work/'ShengDolby.aligned.apk'; output=work/'ShengDolby.apk'
    run([host/'bin/zipalign','-P','16','-f','4',unsigned,aligned])
    signer=host/'framework/apksigner.jar'; security=rom/'build/target/product/security'
    run([jdk/'bin/java','-jar',signer,'sign','--key',security/'platform.pk8','--cert',security/'platform.x509.pem',
         '--min-sdk-version','1','--v1-signing-enabled','true','--v2-signing-enabled','true',
         '--v3-signing-enabled','true','--out',output,aligned])
    verified=run([jdk/'bin/java','-jar',signer,'verify','--verbose','--print-certs','--min-sdk-version','1',output])
    assert 'Verified using v1 scheme (JAR signing): true' in verified
    run([host/'bin/zipalign','-c','-P','16','4',output])
    old=rom/'out/target/product/sheng/system_ext/priv-app/ShengDolby/ShengDolby.apk'
    old_cert=run([jdk/'bin/java','-jar',signer,'verify','--print-certs',old])
    cert=lambda text:re.search(r'certificate SHA-256 digest: ([0-9a-f]+)',text).group(1)
    assert cert(verified)==cert(old_cert)
    scoped_output=output
    if args.normal_build_log:
        assert '#### build completed successfully' in args.normal_build_log.read_text()
        target=rom/'device/xiaomi/sheng/dolby/ShengDolby'
        for path in source.rglob('*'):
            if path.is_file():assert sha(path)==sha(target/path.relative_to(source)),path
        output=old
        normal_verified=run([jdk/'bin/java','-jar',signer,'verify','--verbose','--print-certs','--min-sdk-version','1',output])
        assert 'Verified using v1 scheme (JAR signing): true' in normal_verified
        assert cert(normal_verified)==cert(verified)
        run([host/'bin/zipalign','-c','-P','16','4',output])
        with zipfile.ZipFile(output) as archive:
            for name in archive.namelist():
                if name.endswith('.dex'):assert archive.read(name)[:8]==b'dex\n035\0'
    manifest=run([aapt,'dump','xmltree',output,'--file','AndroidManifest.xml'])
    assert 'android.intent.category.LAUNCHER' not in manifest
    assert 'com.android.settings.action.EXTRA_SETTINGS' in manifest
    assert 'android.media.action.DISPLAY_AUDIO_EFFECT_CONTROL_PANEL' in manifest
    (work/'manifest.txt').write_text(manifest)
    resources_dump=run([aapt,'dump','resources',output]); (work/'resources.txt').write_text(resources_dump)
    receipt=dict(revision=args.revision,scoped_build_passed=True,full_product_build_passed=False,
        normal_module_build_passed=args.normal_build_log is not None,
        normal_build_log_sha256=sha(args.normal_build_log) if args.normal_build_log else None,
        scoped_payload=dict(path=str(scoped_output),sha256=sha(scoped_output)),
        api1_bootstrap_compile_passed=True,api1_runtime_tested=False,dex_version='035',v1_signature_verified=True,
        sdk_byte_audit=sdk_audit,settings_entry_present=True,launcher_entry_present=False,
        platform_certificate_unchanged=True,systemui_changed=False,
        payload=dict(path=str(output),bytes=output.stat().st_size,sha256=sha(output)),
        sources_sha256={str(p):sha(p) for p in [*source.rglob('*'),Path(__file__)] if p.is_file()},
        preaudit_sha256=sha(args.preaudit),commands_sha256=sha(work/'commands.json'))
    (work/'build-review.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
