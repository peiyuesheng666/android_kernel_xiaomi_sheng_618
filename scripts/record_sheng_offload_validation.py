#!/usr/bin/env python3
"""Record verified flash/runtime evidence; speaker confirmation is explicit."""
from pathlib import Path
import argparse
import hashlib
import json

workspace = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--six-speakers-confirmed', action='store_true')
args = parser.parse_args()
evidence = workspace / 'reports/device/system-bringup-r2-20261106-193529'
manifest_path = workspace / 'artifacts/system-audio-offload-sheng-r1/build-result.json'
manifest = json.loads(manifest_path.read_text())
state = (evidence / 'offload-persistent-state.txt').read_text(encoding='utf-8-sig')
hashes = (evidence / 'offload-partition-hashes.txt').read_text(encoding='utf-8-sig')
assert state.splitlines()[0].strip() == '1'
assert 'uid=0(root)' in state and 'Enforcing' in state
assert manifest['tested_pal_sha256'] + '  /vendor/lib64/libar-pal.so' in state
assert sum(line.strip() == 'true' for line in state.splitlines()) == 3
for item in manifest['files']:
    assert item['sha256'] in hashes
    path = manifest_path.parent / item['name']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
assert manifest['unchanged_odm_sha256'] in hashes
repeat = (workspace / 'reports/device/system-bringup-r2-followup-20261106/offload-release-mono-repeat.txt').read_text(encoding='utf-8-sig')
assert repeat.count('COMPLETED position=') == 2
assert repeat.count('PAUSED position=') == repeat.count('RESUMED position=') == 2
assert repeat.count('completed=true') == 2 and 'MEDIA_ERROR' not in repeat
manifest.update({
    'hardware_boot_tested': True,
    'six_speaker_playback_after_reboot': args.six_speakers_confirmed,
    'boot_evidence': str(evidence.relative_to(workspace)).replace('\\', '/'),
    'persistent_runtime_verified': True,
    'stereo_channel_isolation_after_reboot_user_confirmed': True,
    'pre_reboot_stereo_mp3_six_speakers_user_confirmed': True,
    'pre_reboot_mono_mp3_both_sides_user_confirmed': True,
    'pre_reboot_stereo_aac_both_sides_user_confirmed': True,
    'pre_reboot_mono_mp3_two_replays_and_pause_resume_completed': True,
    'untested': ['other_codec_profiles', 'long_term_playback', 'Dolby'],
})
text = json.dumps(manifest, indent=2) + '\n'
manifest_path.write_text(text)
(workspace / 'reports/system-audio-offload-r1.json').write_text(text)
print('Recorded boot, partition readback and runtime verification. Six speakers after reboot:', args.six_speakers_confirmed)
