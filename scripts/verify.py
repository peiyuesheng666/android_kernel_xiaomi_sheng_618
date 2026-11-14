#!/usr/bin/env python3
"""Verify source provenance, release module paths, and any completed build."""
import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import subprocess

project = Path(os.environ['PROJECT_ROOT']).resolve()
root = Path(os.environ['BUILD_ROOT']).resolve()
k = root / 'k618'
expected = json.loads((project / 'provenance/source-files.json').read_text())
charging_fix = json.loads((project / 'provenance/charging-fix.json').read_text())
subprocess.run([os.environ['PYTHON'], project / 'scripts/apply-charging-fix.py', '--check'], check=True)
for name, hashes in charging_fix['files'].items():
    assert expected[name] in (hashes['before'], hashes['after']), name
    expected[name] = hashes['after']
droidspaces_fix = json.loads((project / 'provenance/droidspaces-fix.json').read_text())
subprocess.run([os.environ['PYTHON'], project / 'scripts/apply-droidspaces-fix.py', '--check'], check=True)
for name, hashes in droidspaces_fix['files'].items():
    assert expected[name] in (hashes['before'], hashes['after']), name
    expected[name] = hashes['after']
generated_metadata = {}
scene_fix = json.loads((project / 'provenance/scene-socinfo-fix.json').read_text())
subprocess.run([os.environ['PYTHON'], project / 'scripts/apply-scene-socinfo-fix.py', '--check'], check=True)
for name, hashes in scene_fix['files'].items():
    assert expected[name] in (hashes['before'], hashes['after']), name
    expected[name] = hashes['after']
pen_fix = json.loads((project / 'provenance/pen-release-fix.json').read_text())
subprocess.run([os.environ['PYTHON'], project / 'scripts/apply-pen-release-fix.py', '--check'], check=True)
for name, hashes in pen_fix['files'].items():
    assert expected[name] in (hashes['before'], hashes['after']), name
    expected[name] = hashes['after']
repair_fix = json.loads((project / 'provenance/repair-r85.json').read_text())
subprocess.run([os.environ['PYTHON'], project / 'scripts/apply-repair-r85.py', '--check'], check=True)
for name, hashes in repair_fix['files'].items():
    assert expected.get(name) == hashes['before'], name
    expected[name] = hashes['after']
pen_stability=json.loads((project/'provenance/pen-stability.json').read_text())
subprocess.run([os.environ['PYTHON'],project/'scripts/apply-pen-stability.py','--check'],check=True)
for name,entry in pen_stability['files'].items():
    assert expected[name]==entry['before'],name
    expected[name]=entry['after']
factory_interfaces = json.loads((project / 'provenance/factory-interfaces.json').read_text())
subprocess.run([os.environ['PYTHON'], project / 'scripts/apply-factory-interfaces.py', '--check'], check=True)
for name, hashes in factory_interfaces['files'].items():
    assert expected.get(name) == hashes['before'], name
    expected[name] = hashes['after']
walt_compatibility = json.loads((project / 'provenance/walt-compatibility.json').read_text())
subprocess.run([os.environ['PYTHON'], project / 'scripts/apply-walt-compatibility.py', '--check'], check=True)
for name, hashes in walt_compatibility['files'].items():
    assert expected.get(name) == hashes['before'], name
    expected[name] = hashes['after']
for name, want in expected.items():
    with (root / name).open('rb') as stream:
        got = hashlib.file_digest(stream, 'sha256').hexdigest()
    if got != want:
        # Camera Kbuild regenerates only these three build-identity defines.
        if name == 'k618/vendor/qcom/opensource/camera-kernel/cam_generated_h':
            text = (root / name).read_text()
            pattern = ''.join('#define CAMERA_COMPILE_' + key + ' "[^"\\n]*"\\n'
                              for key in ('TIME', 'BY', 'HOST'))
            assert re.fullmatch(pattern, text), 'Unexpected generated camera header content'
            generated_metadata[name] = {'snapshot_sha256': want, 'compiled_sha256': got}
        else:
            raise SystemExit('Source mismatch: ' + name)
mapping = json.loads((project / 'profiles/module-sources.json').read_text())
assert len(mapping) == 345
for name, relative in mapping.items():
    if relative.startswith('out/'):
        continue
    assert (k / relative).parent.is_dir(), (name, relative)
for name in ('Makefile', 'arch', 'drivers', 'fs', 'include'):
    assert (k / 'ws/common' / name).exists(), name
for path in k.rglob('*'):
    if path.is_symlink():
        assert path.resolve().is_relative_to(root), path
for path in [*project.glob('*.sh'), *(project / 'scripts').glob('*.sh')]:
    subprocess.run(['bash', '-n', path], check=True)
for path in [*(project / 'scripts').glob('*.py'), *(project / 'kernel').glob('*.py')]:
    compile(path.read_text(), str(path), 'exec')
result = {'source_files_verified': len(expected), 'module_count': len(mapping),
          'defconfig': 'sheng_defconfig',
          'stage_scripts': ['buildkernel.sh', 'buildmodules.sh', 'embed.sh', 'mkbootimage.sh'],
          'source_layout_verified': True, 'build_root': str(root), 'fresh_build_verified': False,
          'regenerated_camera_build_metadata': generated_metadata,
          'pen_stability': pen_stability, 'charging_fix': charging_fix, 'droidspaces_fix': droidspaces_fix,
          'scene_socinfo_fix': scene_fix, 'pen_release_fix': pen_fix, 'repair_r87': repair_fix}
result['factory_interfaces'] = factory_interfaces
result['walt_compatibility'] = walt_compatibility
built = k / 'out-gki/build-result.json'
if built.exists():
    build = json.loads(built.read_text())
    network_options = ('IPVLAN', 'MACVLAN', 'VXLAN', 'BRIDGE',
                       'BRIDGE_VLAN_FILTERING', 'VLAN_8021Q', 'OVERLAY_FS')
    config = (k / 'out-gki/kernel.config').read_text().splitlines()
    for option in network_options:
        assert f'CONFIG_{option}=y' in config, option
    result['container_network_filesystem'] = {option: 'y' for option in network_options}
    ipv6_nat_options = ('IP6_NF_NAT', 'IP6_NF_TARGET_MASQUERADE', 'NETFILTER_XT_NAT', 'NETFILTER_XT_TARGET_MASQUERADE', 'IP6_NF_IPTABLES_LEGACY', 'NF_NAT')
    for option in ipv6_nat_options:
        assert f'CONFIG_{option}=y' in config, option
    result['ipv6_nat'] = {option: 'y' for option in ipv6_nat_options}
    mode = os.environ['SHENG_BUILD_MODE']
    assert mode in ('debug', 'release')
    logger = 'CONFIG_SHENG_BOOTLOG=y' in config
    assert logger == (mode == 'debug'), 'Build mode and logger configuration differ'
    embedded_config = subprocess.check_output(['bash', k / 'ws/common/scripts/extract-ikconfig',
                                               k / 'out-gki/Image'], text=True).splitlines()
    assert ('CONFIG_SHENG_BOOTLOG=y' in embedded_config) == logger
    result['build_profile'] = dict(mode=mode, rawdump_enabled=logger,
                                  test_timeout_seconds=int(os.environ['SHENG_TEST_TIMEOUT']) if logger else None,
                                  cmdline=os.environ['SHENG_BOOT_CMDLINE'],
                                  release_default=True)
    for name, want in build['artifacts'].items():
        with (k / 'out-gki' / name).open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == want, name
    with (k / 'out-gki/Image').open('rb') as stream:
        header = stream.read(64)
    assert header[56:60] == b'ARM\x64', 'Invalid ARM64 Image header'
    if build['boot_packaged']:
        unpack = k / 'out-gki/boot-readback'
        subprocess.check_output([os.environ['PYTHON'], project / 'tools/mkbootimg/unpack_bootimg.py',
                                 '--boot_img', k / 'out-gki/boot.img', '--out', unpack])
        assert (unpack / 'ramdisk').stat().st_size == 0
        assert gzip.decompress((unpack / 'kernel').read_bytes()) == (k / 'out-gki/Image').read_bytes()
        boot_data = (k / 'out-gki/boot.img').read_bytes()
        assert boot_data[44:1580].split(b'\0', 1)[0].decode() == os.environ['SHENG_BOOT_CMDLINE']
        if mode == 'release':
            stock = Path(os.environ['STOCK_BOOT'])
            assert hashlib.file_digest(stock.open('rb'), 'sha256').hexdigest() == factory_interfaces['stock_boot_sha256']
            with stock.open('rb') as stream:
                stock_header = stream.read(4096)
            stock_cmdline = stock_header[44:1580].split(b'\0', 1)[0].decode()
            assert stock_cmdline == factory_interfaces['stock_boot_cmdline']
            expected_cmdline = ' '.join(filter(None, (stock_cmdline, walt_compatibility['required_boot_cmdline'])))
            assert os.environ['SHENG_BOOT_CMDLINE'] == expected_cmdline == 'sched_proxy_exec=0'
            assert boot_data[44:1580] == expected_cmdline.encode().ljust(1536, b'\0')
            result['factory_boot_cmdline_base_verified'] = True
            result['walt_boot_cmdline_verified'] = True
    abi = subprocess.check_output([os.environ['PYTHON'], project / 'tools/verify-module-abi.py',
                                   k / 'out-gki', k / 'out-gki/layer/lib/modules'], text=True)
    result.update(fresh_build_verified=True, build=build, module_abi=json.loads(abi))
    btf = json.loads((k / 'out-gki/module-btf-final.json').read_text())
    assert btf['all_modules_passed'] and btf['module_count'] == 345
    for record in btf['modules']:
        with (k / 'out-gki/layer/lib/modules' / record['module']).open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == record['sha256']
        assert set(record['btf']) == {'.BTF', '.BTF.base'}
    result['module_btf'] = {key: value for key, value in btf.items() if key != 'modules'}
    result['source_model'] = 'pinned r76 cache plus repair-r87, pen v4, thermal/idle and full Qualcomm WALT overlays'

else:
    result['build_status'] = 'No completed build in this prepared workspace'
dest = project / 'dist' / os.environ['TAG']
dest.mkdir(parents=True, exist_ok=True)
(dest / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
