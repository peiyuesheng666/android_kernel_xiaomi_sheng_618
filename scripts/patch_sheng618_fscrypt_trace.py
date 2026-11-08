#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Record fscrypt-provisioning ABI metadata, never key bytes or identifiers."""
import difflib
import hashlib
import json
from build_sheng618_upstream import ACK, PROJECT

path = ACK / 'fs/crypto/keyring.c'
receipt = PROJECT / 'reports/kernel618-fscrypt-trace-source.json'
old = '''	if (!fscrypt_valid_key_size(prep->datalen - sizeof(*payload),
				    payload->flags))
		return -EINVAL;'''
new = '''	pr_notice("sheng_fscrypt_abi: provisioning len=%zu header=%zu type=%u flags=0x%x raw=%zu\\n",
		  prep->datalen, sizeof(*payload), payload->type, payload->flags,
		  prep->datalen - sizeof(*payload));
	if (!fscrypt_valid_key_size(prep->datalen - sizeof(*payload),
				    payload->flags)) {
		pr_notice("sheng_fscrypt_abi: rejected provisioning key size\\n");
		return -EINVAL;
	}'''
before = path.read_text()
if receipt.exists() and hashlib.sha256(before.encode()).hexdigest() == json.loads(receipt.read_text())['after']:
    assert before.count(new) == 1
    before = before.replace(new, old, 1)
assert before.count(old) == 1
after = before.replace(old, new, 1)
path.write_text(after)
(PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/fscrypt-abi-trace.patch').write_text(
    ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile='a/fs/crypto/keyring.c', tofile='b/fs/crypto/keyring.c', n=0)))
receipt.write_text(json.dumps(dict(before=hashlib.sha256(before.encode()).hexdigest(),
    after=hashlib.sha256(after.encode()).hexdigest(), key_material_recorded=False,
    behavior='Metadata-only diagnostics, original validation and return values unchanged',
    fields=['total length', 'header length', 'key spec type', 'flags', 'raw length'],
    references=[dict(commit='ff4a6c3bb0f471a9dd186293a47b62c83829b97d', path='fs/crypto/keyring.c',
                    difference='Provisioning size validation depends on new payload flags; get_keyring_key requires exact requested flags'),
                dict(commit='f9ca2b71f6725a0d4f0b1cb2aa553baaea98e74d', path='fs/crypto/keyring.c',
                    difference='LOS 5.15 permits up to 128 bytes regardless of reserved field and has no wrapped flag in provisioning payload'),
                dict(commit='29db5d592c5b577aa9d9611da988a5e071d100dd', path='fs/crypto/keyring.c',
                    difference='MiCode stock uses old zero-reserved provisioning ABI; compare actual payload metadata before changing semantics')]), indent=2) + '\n')
