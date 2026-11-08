#!/usr/bin/env python3
"""Build only the Settings RRO and validate the sheng init file for r29."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
OUT = Path('/root/sheng-lineage/hardware-diagnostics/r29-identity-boot-build-attempt3')
HOST = ROM / 'out/host/linux-x86/bin'
PRODUCT = ROM / 'out/target/product/sheng'
JDK = ROM / 'prebuilts/jdk/jdk21/linux-x86'
ANDROID = '{http://schemas.android.com/apk/res/android}'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert DEVICE == ROM / 'device/xiaomi/sheng'
    pre = OUT.parent / 'r29-prebuild-audit-20261108.json'
    audit = json.loads(pre.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert len(audit['repositories']) == 21
    assert all(r['fetch']['returncode'] == 0 for r in audit['repositories'])
    supplemental = OUT.parent / 'r29-init-build-upstream-audit-20261108.json'
    extra = json.loads(supplemental.read_text())
    assert all(r['passed'] and r['fetch']['returncode'] == 0 for r in extra['repositories'])
    assert {r['path'] for r in extra['repositories']} == {'system/core', 'build/make'}
    OUT.mkdir(exist_ok=False)
    environment = dict(os.environ, JAVA_HOME=str(JDK),
                       PATH=str(JDK / 'bin') + ':' + os.environ['PATH'],
                       LD_LIBRARY_PATH=str(HOST.parent / 'lib64'))
    commands = []

    def run(command):
        command = list(map(str, command))
        result = subprocess.run(command, cwd=ROM, env=environment, capture_output=True, text=True)
        commands.append(dict(command=command, returncode=result.returncode,
                             stdout=result.stdout, stderr=result.stderr))
        (OUT / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    overlay = DEVICE / 'overlay/SettingsResOverlaySheng'
    for locale in ('xml', 'xml-zh'):
        for name in ('my_device_info', 'hardware_info'):
            root = ET.parse(overlay / 'res' / locale / (name + '.xml')).getroot()
            rows = [n for n in root.iter() if n.get(ANDROID + 'key') == 'sheng_codename']
            assert len(rows) == 1 and rows[0].get(ANDROID + 'summary') == 'sheng'
            assert rows[0].get(ANDROID + 'title') == ('设备代号' if locale == 'xml-zh' else 'Device codename')
            for node in root.iter():
                assert all(not value.startswith(('@string/', '@xml/', '@array/'))
                           for value in node.attrib.values()), 'Overlay-local references are unsafe here'
    rc = DEVICE / 'rootdir/etc/init.sm8550.rc'
    assert 'wait /sys/class/thermal/thermal_message/boot_complete' not in rc.read_text()
    kernel = ROM / 'kernel/xiaomi/sm8550/drivers/thermal/mi_thermal_interface.c'
    assert 'boot_complete' not in kernel.read_text()
    assert 'write /sys/devices/virtual/thermal/thermal_message/sconfig 19' in rc.read_text()
    # Use the generated module's actual link flags, rather than regenerating Soong.
    generated = ROM / 'out/soong/build.lineage_sheng.0.ninja'
    content = generated.read_text()
    start = content.index('    flags = --package-id 0x80 --enable-compact-entries')
    flags_line = content[start:].splitlines()[0].removeprefix('    flags = ')
    flags_line = re.sub(r'\$\$\(: [0-9a-f]+\)', '', flags_line)
    flags = shlex.split(flags_line)
    assert flags[:2] == ['--package-id', '0x80']
    assert 'SettingsResOverlaySheng' in flags[flags.index('--manifest') + 1]
    assert '--no-static-lib-packages' in flags
    (OUT / 'generated-link-flags.txt').write_text(flags_line + '\n')
    run([HOST / 'aapt2', 'compile', '--pseudo-localize', '--dir', overlay / 'res',
         '-o', OUT / 'compiled.zip'])
    run([HOST / 'aapt2', 'link', '-o', OUT / 'unsigned.apk', *flags, OUT / 'compiled.zip'])
    security = ROM / 'build/make/target/product/security'
    apk = OUT / 'SettingsResOverlaySheng.apk'
    run([JDK / 'bin/java', '-Djava.library.path=' + str(HOST.parent / 'lib64'),
         '-jar', HOST.parent / 'framework/signapk.jar', '--disable-v1',
         security / 'testkey.x509.pem', security / 'testkey.pk8', OUT / 'unsigned.apk', apk])
    run([HOST / 'apksigner', 'verify', '--verbose', '--print-certs', apk])
    target = PRODUCT / 'system_ext/priv-app/Settings/Settings.apk'
    run([HOST / 'idmap2', 'create', '--target-apk-path', target,
         '--overlay-apk-path', apk, '--idmap-path', OUT / 'settings.idmap', '--policy', 'odm'])
    contexts = PRODUCT / 'vendor/etc/selinux/vendor_property_contexts'
    run([HOST / 'host_init_verifier', '-p', PRODUCT / 'vendor/etc/passwd',
         '-p', PRODUCT / 'system/etc/passwd', '--property-contexts=' + str(contexts), rc])
    run(['python3', DEVICE / 'tools/tablet_probe/build_probe.py', '--rom', ROM,
         '--output', OUT / 'probe'])
    outputs = {'odm': {'overlay/SettingsResOverlaySheng.apk': apk},
               'vendor': {'etc/init/init.sm8550.rc': rc}}
    # Assembly touches only these two product files; no public source or graph is changed.
    for partition, entries in outputs.items():
        for relative, source in entries.items():
            target = PRODUCT / partition / relative
            assert target.is_file() and not target.is_symlink()
            shutil.copyfile(source, target)
            assert sha(target) == sha(source)
    report = dict(revision=29, scoped_module_build_passed=True, full_product_build_passed=False,
                  host_init_verifier_passed=True, host_idmap_overlayable_enforced=True,
                  source_sha256={str(p.relative_to(DEVICE)): sha(p) for p in
                      [*sorted(overlay.rglob('*.xml')), overlay / 'Android.bp', rc,
                       DEVICE / 'tools/tablet_probe/ResourceProbe.java', Path(__file__)]},
                  reviewed_sha256={p: {r: sha(s) for r, s in entries.items()}
                                   for p, entries in outputs.items()},
                  prebuild_audit_sha256=sha(pre), supplemental_audit_sha256=sha(supplemental),
                  generated_ninja_sha256=sha(generated), command_log_sha256=sha(OUT / 'commands.json'),
                  previous_attempts=[dict(path=str(OUT.parent / 'r29-identity-boot-build'),
                      failure='host_init_verifier help advertised an underscore; actual option uses a hyphen',
                      product_files_changed=False), dict(
                      path=str(OUT.parent / 'r29-identity-boot-build-attempt2'),
                      failure='report source glob also matched the res/xml directory',
                      build_and_parser_checks_passed=True, product_files_changed=True)],
                  systemui_changed=False, installed=False, runtime_verified=False)
    review = DEVICE / 'docs/r29-identity-boot-build-review-20261108.json'
    assert not review.exists()
    review.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
