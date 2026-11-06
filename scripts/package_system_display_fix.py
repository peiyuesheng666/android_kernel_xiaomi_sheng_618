#!/usr/bin/env python3
"""Patch the installed OTA's ODM display defaults, preserving partition size."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from extract_ota_boot_images import extract, sha256_file

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
product = rom / 'out/target/product/sheng'
host = rom / 'out/host/linux-x86/bin'
destination = workspace / 'artifacts/system-display-fix-sheng-lineage-24.0-r1'
assert not destination.exists()
assert shutil.disk_usage('/mnt/c').free > 20 * 1024**3
build = Path('/root/sheng-lineage/system-display-fix') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
build.mkdir(parents=True)
manifest = json.loads((workspace / 'reports/ota-install-manifest-audit.json').read_text())
partitions = {item['name']: item for item in manifest['partitions']}


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


# Reuse the already-generated overlay build rule. Regenerating the entire Soong
# graph for two integer resources exceeds this host's physical memory.
relative = 'overlay/FrameworkResOverlaySheng.apk'
original_overlay = product / 'odm' / relative
original_resources = run([host / 'aapt2', 'dump', 'resources', original_overlay],
                         capture_output=True, text=True).stdout
module_root = rom / 'out/soong/.intermediates/device/xiaomi/sheng/overlay/FrameworkResOverlaySheng/FrameworkResOverlaySheng/android_common'
ninja = (rom / 'out/soong/build.lineage_sheng.0.ninja').read_text()
section = ninja.split('# Module:  FrameworkResOverlaySheng\n', 1)[1].split('# Module:', 1)[0]
link_flags = re.search(r'^    flags = (--enable-compact-entries[^\n]+)$', section, re.M).group(1)
link_flags = re.sub(r'\$\$\(: [0-9a-f]+\)', '', link_flags)
compiled = build / 'resources'
compiled.mkdir()
source_resources = rom / 'device/xiaomi/sheng/overlay/FrameworkResOverlaySheng/res'
run([host / 'aapt2', 'compile', '--pseudo-localize', '--dir', source_resources, '-o', compiled])
unsigned = build / 'overlay-unsigned.apk'
run([host / 'aapt2', 'link', *shlex.split(link_flags), '-o', unsigned, *sorted(compiled.glob('*.flat'))], cwd=rom)
overlay = build / 'FrameworkResOverlaySheng.apk'
run([rom / 'prebuilts/jdk/jdk21/linux-x86/bin/java',
     '-Djava.library.path=' + str(host.parent / 'lib64'), '-jar', host.parent / 'framework/signapk.jar',
     '--disable-v1', rom / 'build/make/target/product/security/testkey.x509.pem',
     rom / 'build/make/target/product/security/testkey.pk8', unsigned, overlay])
resources = run([host / 'aapt2', 'dump', 'resources', overlay], capture_output=True, text=True).stdout
expected_resources = original_resources
for name in ('config_defaultRefreshRate', 'config_defaultPeakRefreshRate'):
    expected_resources, count = re.subn(r'(\b' + name + r'\b[^\n]*\n\s*\(\) )144\b', r'\g<1>60', expected_resources)
    assert count == 1, name
assert expected_resources == resources, 'Unexpected resource changes'

base = extract(('odm', 'vbmeta'))
raw_base = Path(base['odm']['path'])
assert sha256_file(raw_base) == partitions['odm']['sha256']
staging = build / 'odm'
run([host / 'fsck.erofs', '-d0', '--extract=' + str(staging), '--preserve', raw_base],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
for name in ('config_defaultRefreshRate', 'config_defaultPeakRefreshRate'):
    assert re.search(r'\b' + name + r'\b[^\n]*\n\s*\(\) 60\b', resources), name
shutil.copyfile(overlay, staging / relative)
props_path = staging / 'etc/build.prop'
assert props_path.is_file()
props = props_path.read_text()
assert 'vendor.display.disable_cwb_idle_fallback=' not in props
props_path.write_text(props.rstrip() + '\n\n# sheng video-mode scanout cannot clone the idle CWB encoder.\n'
                      'vendor.display.disable_cwb_idle_fallback=1\n')
packaging = product / 'obj/PACKAGING/odm_intermediates'
properties = build / 'odm_image_info.txt'
fs_config = product / 'obj/PACKAGING/target_files_intermediates/lineage_sheng-target_files/META/odm_filesystem_config.txt'
assert fs_config.is_file()
properties.write_text((packaging / 'odm_image_info.txt').read_text().rstrip() +
                      '\nuse_dynamic_partition_size=false\nodm_size=' + str(partitions['odm']['bytes']) +
                      '\nfs_config=' + str(fs_config) + '\n')
environment = dict(os.environ)
environment['PATH'] = str(host) + ':' + environment['PATH']
image = build / 'odm.img'
with (build / 'build.log').open('w') as output:
    run([host / 'build_image', '--input-directory-filter-file', packaging / 'file_list.txt',
         staging, properties, image, product / 'system'], cwd=rom, env=environment,
        stdout=output, stderr=subprocess.STDOUT)
assert image.stat().st_size == partitions['odm']['bytes'], 'Partition size changed'
readback = build / 'readback'
run([host / 'fsck.erofs', '-d0', '--extract=' + str(readback), '--preserve', image],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
assert sha256_file(readback / relative) == sha256_file(overlay)
assert (readback / 'etc/build.prop').read_bytes() == props_path.read_bytes()


def tree(root):
    entries = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            entries[str(path.relative_to(root))] = ('link', os.readlink(path))
        elif path.is_file():
            stat = path.stat()
            entries[str(path.relative_to(root))] = ('file', sha256_file(path), stat.st_uid,
                                                  stat.st_gid, stat.st_mode & 0o7777)
    return entries


assert tree(staging) == tree(readback), 'File contents or ownership changed during packing'
avbtool = host / 'avbtool'
run([avbtool, 'verify_image', '--image', image], capture_output=True)
new_vbmeta = build / 'vbmeta.img'
base_vbmeta = Path(base['vbmeta']['path'])
old_info = run([avbtool, 'info_image', '--image', base_vbmeta], capture_output=True, text=True).stdout
assert re.search(r'^Flags:\s+3$', old_info, re.M)
# include_descriptors_from_image deliberately omits chain descriptors. Preserve
# the complete original descriptor sequence, replacing only ODM's hashtree.
sys.path.insert(0, str(rom / 'external/avb'))
import avbtool as avb_module
avb = avb_module.Avb()
_, original_header, original_descriptors, _ = avb._parse_image(avb_module.ImageHandler(str(base_vbmeta), read_only=True))
_, _, odm_descriptors, _ = avb._parse_image(avb_module.ImageHandler(str(image), read_only=True))
replacement = [desc for desc in odm_descriptors if isinstance(desc, avb_module.AvbHashtreeDescriptor)
               and desc.partition_name == 'odm']
assert len(replacement) == 1
descriptors = [replacement[0] if isinstance(desc, avb_module.AvbHashtreeDescriptor)
               and desc.partition_name == 'odm' else desc for desc in original_descriptors]
blob = avb._generate_vbmeta_blob(
    algorithm_name='SHA256_RSA4096', key_path=str(rom / 'external/avb/test/data/testkey_rsa4096.pem'),
    public_key_metadata_path=None, descriptors=descriptors, chain_partitions_use_ab=None,
    chain_partitions_do_not_use_ab=None, rollback_index=original_header.rollback_index,
    flags=original_header.flags, rollback_index_location=original_header.rollback_index_location,
    props=None, props_from_file=None, kernel_cmdlines=None, setup_rootfs_from_kernel=None,
    ht_desc_to_setup=None, include_descriptors_from_image=None, signing_helper=None,
    signing_helper_with_files=None, release_string=original_header.release_string,
    append_to_release_string=None, required_libavb_version_minor=original_header.required_libavb_version_minor)
assert len(blob) <= partitions['vbmeta']['bytes']
new_vbmeta.write_bytes(blob + b'\0' * (partitions['vbmeta']['bytes'] - len(blob)))
_, new_header, new_descriptors, _ = avb._parse_image(avb_module.ImageHandler(str(new_vbmeta), read_only=True))
assert avb_module.verify_vbmeta_signature(new_header, blob)
assert len(new_descriptors) == len(original_descriptors)
changed = [(old, new) for old, new in zip(original_descriptors, new_descriptors) if old.encode() != new.encode()]
assert len(changed) == 1 and isinstance(changed[0][0], avb_module.AvbHashtreeDescriptor)
assert changed[0][0].partition_name == 'odm'
new_info = run([avbtool, 'info_image', '--image', new_vbmeta], capture_output=True, text=True).stdout
assert new_vbmeta.stat().st_size == partitions['vbmeta']['bytes']
for info in (old_info, new_info):
    assert '2597c218aae470a130f61162feaae70afd97f011' in info
    assert re.search(r'^Flags:\s+3$', info, re.M)


def roots(info):
    return dict(re.findall(r'Partition Name:\s+(\S+).*?Root Digest:\s+(\S+)',
                           info.split('    Hashtree descriptor:', 1)[1], re.S))


old_roots, new_roots = roots(old_info), roots(new_info)
assert old_roots.keys() == new_roots.keys()
assert old_roots['odm'] != new_roots['odm']
assert all(old_roots[name] == new_roots[name] for name in old_roots if name != 'odm')
(build / 'vbmeta-before.txt').write_text(old_info)
(build / 'vbmeta-after.txt').write_text(new_info)
destination.mkdir()
files = []
for path in (image, new_vbmeta):
    shutil.copyfile(path, destination / path.name)
    assert sha256_file(destination / path.name) == sha256_file(path)
    files.append({'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha256_file(path)})
report = {'files': files, 'work_dir': str(build), 'base_matches_installed_ota': True,
          'changed_files': ['etc/build.prop', relative], 'default_refresh_rate': 60,
          'default_peak_refresh_rate': 60, 'disable_cwb_idle_fallback': True,
          'partition_size_unchanged': image.stat().st_size,
          'readback_content_and_ownership_verified': True, 'overlay_only_two_values_changed': True,
          'avb_image_verified': True, 'vbmeta_other_roots_unchanged': True,
          'vbmeta_flags_preserved': 3, 'vbmeta_signature_verified': True,
          'vbmeta_all_original_chain_descriptors_preserved': True, 'hardware_boot_tested': False}
(destination / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(workspace / 'reports/system-display-fix-r1.json').write_text(json.dumps(report, indent=2) + '\n')
(destination / 'SHA256SUMS').write_text(''.join(item['sha256'] + '  ' + item['name'] + '\n' for item in files))
print(json.dumps(report, indent=2))
