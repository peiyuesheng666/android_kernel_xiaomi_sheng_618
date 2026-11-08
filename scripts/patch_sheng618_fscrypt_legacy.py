#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Support stock 5.15 provisioning payloads through the existing Android wrapped ioctl ABI."""
import difflib
import hashlib
import json
from build_sheng618_upstream import ACK, PROJECT

path = ACK / 'fs/crypto/keyring.c'
receipt = PROJECT / 'reports/kernel618-fscrypt-legacy-source.json'
changes = [
    ('\tconst struct fscrypt_provisioning_key_payload *payload = prep->data;\n',
     '\tconst struct fscrypt_provisioning_key_payload *payload = prep->data;\n\tu32 size_flags;\n'),
    ('\tif (!fscrypt_valid_key_size(prep->datalen - sizeof(*payload),\n\t\t\t\t    payload->flags)) {',
     '\tsize_flags = payload->flags;\n'
     '#ifdef CONFIG_SHENG_LEGACY_FSCRYPT_PROVISIONING\n'
     '\t/* 5.15 used zero reserved here, including for up to 128 wrapped bytes.\n'
     '\t * Actual interpretation is checked when the ioctl retrieves this key.\n'
     '\t */\n'
     '\tif (!payload->flags)\n\t\tsize_flags = FSCRYPT_ADD_KEY_FLAG_HW_WRAPPED;\n'
     '#endif\n'
     '\tif (!fscrypt_valid_key_size(prep->datalen - sizeof(*payload),\n\t\t\t\t    size_flags)) {'),
    ('\tconst struct fscrypt_provisioning_key_payload *payload;\n\tint err;\n',
     '\tconst struct fscrypt_provisioning_key_payload *payload;\n'
     '\tbool legacy_wrapped = false;\n\tint err;\n'),
    ('\tif (payload->type != type || payload->flags != flags)\n\t\tgoto bad_key;\n\n'
     '\tsecret->size = key->datalen - sizeof(*payload);',
     '#ifdef CONFIG_SHENG_LEGACY_FSCRYPT_PROVISIONING\n'
     '\t/* Only the already-validated old Android __flags ioctl may interpret\n'
     '\t * a zero-reserved provisioning payload as hardware-wrapped material.\n'
     '\t */\n'
     '\tlegacy_wrapped = secret->android_compat && !payload->flags &&\n'
     '\t\tflags == FSCRYPT_ADD_KEY_FLAG_HW_WRAPPED;\n'
     '#endif\n'
     '\tif (payload->type != type ||\n'
     '\t    (payload->flags != flags && !legacy_wrapped))\n\t\tgoto bad_key;\n\n'
     '\tif (!fscrypt_valid_key_size(key->datalen - sizeof(*payload), flags))\n'
     '\t\tgoto bad_key;\n'
     '\tsecret->size = key->datalen - sizeof(*payload);'),
]
before = path.read_text()
if receipt.exists() and hashlib.sha256(before.encode()).hexdigest() == json.loads(receipt.read_text())['after']:
    for old, new in reversed(changes):
        assert before.count(new) == 1
        before = before.replace(new, old, 1)
assert 'sheng_fscrypt_abi: provisioning' in before, 'Apply metadata trace before first legacy patch'
after = before
for old, new in changes:
    assert after.count(old) == 1, old
    after = after.replace(old, new, 1)
path.write_text(after)
(PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/fscrypt-legacy-provisioning.patch').write_text(
    ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile='a/fs/crypto/keyring.c', tofile='b/fs/crypto/keyring.c', n=0)))
kconfig = ACK / 'fs/crypto/Kconfig'
if 'config SHENG_LEGACY_FSCRYPT_PROVISIONING\n' not in kconfig.read_text():
    with kconfig.open('a') as stream:
        stream.write('\nconfig SHENG_LEGACY_FSCRYPT_PROVISIONING\n'
                     '\tbool "Sheng stock Android wrapped provisioning ABI"\n\tdepends on FS_ENCRYPTION\n')
receipt.write_text(json.dumps(dict(before=hashlib.sha256(before.encode()).hexdigest(),
    after=hashlib.sha256(after.encode()).hexdigest(),
    hardware_evidence='crypto-r15 run a293e563889714e0: total108/header8/type2/flags0/raw100 rejected at provisioning size check',
    behavior='Permit old zero-reserved provisioning up to wrapped maximum; only existing Android __flags ioctl enables wrapped interpretation. Native raw size and raw/wrapped checks remain enforced at retrieval.',
    key_material_logged=False, modifies_userspace_or_keys_on_disk=False,
    references=[dict(commit='ff4a6c3bb0f471a9dd186293a47b62c83829b97d',
                     path='fs/crypto/keyring.c', result='Retain existing secret.android_compat path and original Android KDF context'),
                dict(commit='f9ca2b71f6725a0d4f0b1cb2aa553baaea98e74d',
                     path='fs/crypto/keyring.c', result='LOS 5.15 accepts 128-byte provisioning and checks old ioctl wrapped flags'),
                dict(commit='29db5d592c5b577aa9d9611da988a5e071d100dd',
                     path='fs/crypto/keyring.c', result='MiCode 5.15 has the same old reserved-field representation')]), indent=2) + '\n')
