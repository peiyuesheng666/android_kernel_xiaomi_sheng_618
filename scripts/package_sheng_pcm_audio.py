#!/usr/bin/env python3
"""Package the verified basic PCM speaker fix, changing vendor and vbmeta only."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
product = rom / 'out/target/product/sheng'
host = rom / 'out/host/linux-x86/bin'
parser = argparse.ArgumentParser()
parser.add_argument('--revision', type=int, default=2, choices=(2,))
args = parser.parse_args()
base_dir = workspace / 'artifacts/system-audio-pcm-sheng-r1'
destination = workspace / f'artifacts/system-audio-pcm-sheng-r{args.revision}'
build = Path(f'/root/sheng-lineage/system-audio-pcm-r{args.revision}')
build.mkdir(exist_ok=True)
destination.mkdir(exist_ok=True)
sources = workspace / 'device/xiaomi/sheng'

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)

def tree(root):
    result = {}
    for path in root.rglob('*'):
        name = str(path.relative_to(root))
        if path.is_symlink():
            result[name] = ('link', os.readlink(path))
        elif path.is_file():
            stat = path.stat()
            result[name] = ('file', sha(path), stat.st_uid, stat.st_gid, stat.st_mode & 0o7777)
    return result

base_manifest = json.loads((base_dir / 'build-result.json').read_text())
base_files = dict(base_manifest['base_files'])
base_files.update({item['partition']: item for item in base_manifest['files']})
for item in base_manifest['files']:
    partition = item['partition']
    image = base_dir / item['name']
    assert image.stat().st_size == item['bytes'] and sha(image) == item['sha256'], partition

# Correct the explanatory comment to match SPF's output-major ABI. The tested
# matrix stays unchanged: slots 0/1 receive L, slots 2/3 receive R.
pal = rom / 'hardware/qcom-caf/sm8550/audio/pal'
source = pal / 'session/src/PayloadBuilder.cpp'
text = source.read_text()
old = '''    // Input rows, output columns, as documented in populateChannelMixerCoeff.
    // L -> FL and LB; R -> FR and RB, with Q14 unity and no extra gain.
'''
new = '''    // SPF coefficients have OUTPUT rows and INPUT columns. On sheng the
    // physical left speakers use TDM slots 0/1 and right speakers use 2/3.
    // Keep both slots on each physical side on the same stereo input.
    // Verified with isolated left/right PCM tones; Q14 unity adds no gain.
'''
if old in text:
    source.write_text(text.replace(old, new, 1))
assert new in source.read_text()
patch = run(['git', '-C', pal, 'diff', '--', 'session/src/Session.cpp',
             'session/src/PayloadBuilder.cpp', 'session/inc/PayloadBuilder.h'], capture_output=True).stdout
assert b'payloadShengStereoQuadCoeff' in patch
(workspace / 'patches/sheng-pcm-stereo-quad-coeff.patch').write_bytes(patch)

tested_library = workspace / 'artifacts/audio-diagnostics-sheng/libar-pal-pcm-quad-coeff.so'
assert sha(tested_library) == 'bea27cd5c33d0610b516f53dba9cbb1997bc59aedc243fc808087e78a554cf4b'
assert sha(product / 'vendor/lib64/libar-pal.so') == sha(tested_library)
effects = sources / 'configs/audio/sku_kalama/audio_effects.xml'
assert '<apply effect="dlb_music_listener"' not in effects.read_text()
assert '<apply effect="music_helper"' in effects.read_text()
policy = sources / 'configs/audio/sku_kalama/audio_policy_configuration.xml'
policy_tree = ET.fromstring(policy.read_text())
speaker_routes = [item for item in policy_tree.iter('route') if item.get('sink') == 'Speaker']
assert len(speaker_routes) == 1
speaker_sources = speaker_routes[0].get('sources').split(',')
assert 'compressed_offload' not in speaker_sources and 'deep_buffer' in speaker_sources
stage = build / 'vendor'
if stage.exists():
    raise SystemExit('The package staging directory already exists; inspect it before rebuilding.')
base_vendor = base_dir / 'vendor.img'
run([host / 'fsck.erofs', '-d0', '--extract=' + str(stage), '--preserve', base_vendor],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
before = tree(stage)
changes = {
    'lib64/libar-pal.so': tested_library,
    'etc/audio/sku_kalama/audio_effects.xml': effects,
    'etc/audio_effects.xml': effects,
    'etc/audio/sku_kalama/audio_policy_configuration.xml': policy,
}
for relative, path in changes.items():
    target = stage / relative
    original = target.stat()
    shutil.copyfile(path, target)
    os.chmod(target, original.st_mode & 0o7777)
    os.chown(target, original.st_uid, original.st_gid)
properties = stage / 'build.prop'
assert properties.is_file()
keys = ('audio.deep_buffer.media', 'vendor.audio.sheng.stereo_quad_coeff')
desired = dict(line.split('=', 1) for line in (sources / 'properties/vendor.prop').read_text().splitlines()
               if any(line.startswith(key + '=') for key in keys))
assert set(desired) == set(keys)
lines = properties.read_text().splitlines()
lines = [line for line in lines if not any(line.startswith(key + '=')
         for key in (*keys, 'audio.offload.disable'))]
properties.write_text('\n'.join(lines) + '\n' + '\n'.join(key + '=' + desired[key] for key in keys) + '\n')
after = tree(stage)
changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
assert changed <= set(changes) | {'build.prop'}, changed
assert 'etc/audio/sku_kalama/audio_policy_configuration.xml' in changed

packaging = product / 'obj/PACKAGING/vendor_intermediates'
config = product / ('obj/PACKAGING/target_files_intermediates/'
                    'lineage_sheng-target_files/META/vendor_filesystem_config.txt')
file_list = build / 'vendor_file_list.txt'
# The original OTA packaging list predates bring-up additions (e.g. THP).
# Include every file in the installed base so this audio update retains them.
original_list = (packaging / 'file_list.txt').read_text().splitlines()
file_list.write_text('\n'.join(sorted(set(original_list) | set(before))) + '\n')
for relative in changed:
    assert any(line.startswith('vendor/' + relative + ' ') for line in config.read_text().splitlines()), relative
info = build / 'vendor_image_info.txt'
info.write_text((packaging / 'vendor_image_info.txt').read_text().rstrip() +
                '\nuse_dynamic_partition_size=false\nvendor_size=' + str(base_files['vendor']['bytes']) +
                '\nfs_config=' + str(config) + '\n')
vendor = build / 'vendor.img'
environment = dict(os.environ)
environment['PATH'] = str(host) + ':' + environment['PATH']
with (build / 'vendor-build.log').open('w') as output:
    run([host / 'build_image', '--input-directory-filter-file', file_list,
         stage, info, vendor, product / 'system'], cwd=rom, env=environment,
        stdout=output, stderr=subprocess.STDOUT)
assert vendor.stat().st_size == base_files['vendor']['bytes']
readback = build / 'vendor-readback'
run([host / 'fsck.erofs', '-d0', '--extract=' + str(readback), '--preserve', vendor],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
assert tree(readback) == tree(stage)
run([host / 'avbtool', 'verify_image', '--image', vendor], capture_output=True)

sys.path.insert(0, str(rom / 'external/avb'))
import avbtool as avb_module
avb = avb_module.Avb()
_, header, old_descriptors, _ = avb._parse_image(avb_module.ImageHandler(str(base_dir / 'vbmeta.img'), read_only=True))
_, _, vendor_descriptors, _ = avb._parse_image(avb_module.ImageHandler(str(vendor), read_only=True))
vendor_descriptor = [item for item in vendor_descriptors
                     if isinstance(item, avb_module.AvbHashtreeDescriptor) and item.partition_name == 'vendor']
assert len(vendor_descriptor) == 1
descriptors = [vendor_descriptor[0] if isinstance(item, avb_module.AvbHashtreeDescriptor) and
               item.partition_name == 'vendor' else item for item in old_descriptors]
blob = avb._generate_vbmeta_blob(
    algorithm_name='SHA256_RSA4096', key_path=str(rom / 'external/avb/test/data/testkey_rsa4096.pem'),
    public_key_metadata_path=None, descriptors=descriptors, chain_partitions_use_ab=None,
    chain_partitions_do_not_use_ab=None, rollback_index=header.rollback_index, flags=header.flags,
    rollback_index_location=header.rollback_index_location, props=None, props_from_file=None,
    kernel_cmdlines=None, setup_rootfs_from_kernel=None, ht_desc_to_setup=None,
    include_descriptors_from_image=None, signing_helper=None, signing_helper_with_files=None,
    release_string=header.release_string, append_to_release_string=None,
    required_libavb_version_minor=header.required_libavb_version_minor)
vbmeta = build / 'vbmeta.img'
assert len(blob) <= base_files['vbmeta']['bytes']
vbmeta.write_bytes(blob + b'\0' * (base_files['vbmeta']['bytes'] - len(blob)))
_, new_header, new_descriptors, _ = avb._parse_image(avb_module.ImageHandler(str(vbmeta), read_only=True))
assert new_header.flags == header.flags == 3
assert avb_module.verify_vbmeta_signature(new_header, blob)
assert len(new_descriptors) == len(old_descriptors)
for old, new in zip(old_descriptors, new_descriptors):
    if old.encode() != new.encode():
        assert isinstance(old, avb_module.AvbHashtreeDescriptor) and old.partition_name == 'vendor'
assert any(isinstance(item, avb_module.AvbChainPartitionDescriptor) and
           item.partition_name == 'vbmeta_system' for item in new_descriptors)

files = []
for partition, image in (('vendor', vendor), ('vbmeta', vbmeta)):
    target = destination / image.name
    shutil.copyfile(image, target)
    assert sha(target) == sha(image)
    files.append({'partition': partition, 'name': image.name, 'bytes': image.stat().st_size,
                  'sha256': sha(image)})
report = {'files': files, 'work_dir': str(build), 'base_files': base_files,
          'changed_files': sorted(changed), 'unchanged_partition_sizes': True,
          'readback_content_and_ownership_verified': True, 'avb_signatures_verified': True,
          'all_original_chain_descriptors_preserved': True,
          'unchanged_odm_sha256': base_files['odm']['sha256'],
          'speaker_offload_excluded_by_policy': True,
          'hardware_boot_tested': False, 'six_speaker_playback_after_reboot': False}
(destination / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
(workspace / f'reports/system-audio-pcm-r{args.revision}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
