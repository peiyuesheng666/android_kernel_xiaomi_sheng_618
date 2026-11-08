#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarize actual stock Camera app stream progress without image content."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from test_sheng618_hardware import ROOT

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', required=True)
parser.add_argument('--folder', required=True, type=Path)
parser.add_argument('--camera', choices=['0', '1'], required=True)
options = parser.parse_args()
folder = options.folder.resolve()
assert folder.is_relative_to((ROOT/'reports/device'/('kernel618-'+options.revision)).resolve())
samples = []
for path in sorted(folder.glob('camera-*.txt')):
    text = path.read_text(errors='replace')
    section = text.split('== Camera device '+options.camera+' dynamic info: ==',1)
    streams = []
    if len(section) == 2 and 'Device dump:' in section[1]:
        dynamic = section[1].split('Device dump:',1)[1].split('Camera3 Buffer Manager:',1)[0]
        for part in re.split(r'Stream\[(\d+)\]: Output',dynamic)[1:][1::2]:
            frames = re.search(r'Frames produced: (\d+)',part)
            dims = re.search(r'Dims: (\d+) x (\d+), format (\S+)',part)
            if frames and dims:
                streams.append(dict(frames=int(frames[1]),width=int(dims[1]),height=int(dims[2]),format=dims[3]))
    samples.append(dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),streams=streams))
progress = [max((s['frames'] for s in item['streams']), default=0) for item in samples]
report = dict(revision=options.revision,camera=options.camera,evidence=str(folder.relative_to(ROOT)),samples=samples,
    maximum_frames_by_sample=progress,real_preview_stream_progress=len(progress)>1 and progress[-1]>progress[0] and progress[-1]>=10,
    photos_saved=False,scope='Stock app preview only; still photography, video and visual quality not validated')
(ROOT/'reports'/('kernel618-'+options.revision+'-stock-camera-'+options.camera+'.json')).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
