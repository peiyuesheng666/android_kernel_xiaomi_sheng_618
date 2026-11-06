#!/usr/bin/env python3
"""Keep every original AVB descriptor, changing only ODM's hashtree descriptor."""
import hashlib
import json
from pathlib import Path
import sys

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
sys.path.insert(0, str(rom / 'external/avb'))
import avbtool

directory = workspace / 'artifacts/system-display-fix-sheng-lineage-24.0-r1'
original = Path('/root/sheng-lineage/ota-boot-audit/vbmeta.img')
avb = avbtool.Avb()
_, original_header, original_descriptors, _ = avb._parse_image(avbtool.ImageHandler(str(original), read_only=True))
_, _, odm_descriptors, _ = avb._parse_image(avbtool.ImageHandler(str(directory / 'odm.img'), read_only=True))
replacement = [desc for desc in odm_descriptors if isinstance(desc, avbtool.AvbHashtreeDescriptor)
               and desc.partition_name == 'odm']
assert len(replacement) == 1
descriptors = [replacement[0] if isinstance(desc, avbtool.AvbHashtreeDescriptor)
               and desc.partition_name == 'odm' else desc for desc in original_descriptors]
chain = [desc for desc in descriptors if isinstance(desc, avbtool.AvbChainPartitionDescriptor)]
assert len(chain) == 1 and chain[0].partition_name == 'vbmeta_system'
assert chain[0].rollback_index_location == 1
assert hashlib.sha1(chain[0].public_key).hexdigest() == 'cdbb77177f731920bbe0a0f94f84d9038ae0617d'
release = original_header.release_string
if isinstance(release, bytes):
    release = release.rstrip(b'\0').decode()
blob = avb._generate_vbmeta_blob(
    algorithm_name='SHA256_RSA4096', key_path=str(rom / 'external/avb/test/data/testkey_rsa4096.pem'),
    public_key_metadata_path=None, descriptors=descriptors,
    chain_partitions_use_ab=None, chain_partitions_do_not_use_ab=None,
    rollback_index=original_header.rollback_index, flags=original_header.flags,
    rollback_index_location=original_header.rollback_index_location,
    props=None, props_from_file=None, kernel_cmdlines=None,
    setup_rootfs_from_kernel=None, ht_desc_to_setup=None,
    include_descriptors_from_image=None, signing_helper=None, signing_helper_with_files=None,
    release_string=release, append_to_release_string=None,
    required_libavb_version_minor=original_header.required_libavb_version_minor)
assert len(blob) <= original.stat().st_size
target = directory / 'vbmeta-chain-fixed.img'
target.write_bytes(blob + b'\0' * (original.stat().st_size - len(blob)))
_, new_header, new_descriptors, _ = avb._parse_image(avbtool.ImageHandler(str(target), read_only=True))
assert avbtool.verify_vbmeta_signature(new_header, blob)
assert len(new_descriptors) == len(original_descriptors)
changed = []
for old, new in zip(original_descriptors, new_descriptors):
    if old.encode() != new.encode():
        assert isinstance(old, avbtool.AvbHashtreeDescriptor) and old.partition_name == 'odm'
        changed.append('odm')
assert changed == ['odm']
sha = hashlib.sha256(target.read_bytes()).hexdigest()
report = {'file': str(target), 'bytes': target.stat().st_size, 'sha256': sha,
          'signature_verified': True, 'all_original_chain_descriptors_preserved': True,
          'only_changed_descriptor': 'odm', 'original_flags_preserved': original_header.flags,
          'hardware_boot_tested': False}
(directory / 'vbmeta-chain-fixed.json').write_text(json.dumps(report, indent=2) + '\n')
(workspace / 'reports/display-vbmeta-chain-repair.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
