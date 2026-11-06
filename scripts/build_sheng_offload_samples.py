#!/usr/bin/env python3
"""Generate low-volume known-channel AAC/mono MP3 samples and playback probe."""
from pathlib import Path
import math
import os
import struct
import subprocess
import wave

workspace = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
output = Path('/root/sheng-lineage/audio-offload-probe')
output.mkdir(exist_ok=True)
destination = workspace / 'artifacts/audio-diagnostics-sheng'
for name, rate, channels, duration in (('stereo', 48000, 2, 90), ('mono', 44100, 1, 45)):
    if (output / (name + '.wav')).exists():
        continue
    with wave.open(str(output / (name + '.wav')), 'wb') as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        for second in range(duration):
            data = bytearray()
            for i in range(rate):
                frame = second * rate + i
                left = int(2000 * math.sin(2 * math.pi * 500 * frame / rate))
                if channels == 1:
                    data.extend(struct.pack('<h', left))
                else:
                    right = int(2000 * math.sin(2 * math.pi * 800 * frame / rate))
                    if second < 4: right = 0
                    elif second < 8: left = 0
                    data.extend(struct.pack('<hh', left, right))
            audio.writeframes(data)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(output / 'stereo.wav'),
                '-c:a', 'aac', '-b:a', '128k', str(destination / 'sheng-aac-stereo-probe.m4a')], check=True)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(output / 'mono.wav'),
                '-c:a', 'libmp3lame', '-b:a', '128k', str(destination / 'sheng-mp3-mono-probe.mp3')], check=True)
stereo_isolation = output / 'stereo-isolation.wav'
with wave.open(str(stereo_isolation), 'wb') as audio:
    audio.setnchannels(2)
    audio.setsampwidth(2)
    audio.setframerate(44100)
    for second in range(72):
        data = bytearray()
        for i in range(44100):
            frame = second * 44100 + i
            left = int(2000 * math.sin(2 * math.pi * 500 * frame / 44100))
            right = int(2000 * math.sin(2 * math.pi * 800 * frame / 44100))
            if second < 18 or 54 <= second < 63:
                right = 0
            elif second < 36 or second >= 63:
                left = 0
            data.extend(struct.pack('<hh', left, right))
        audio.writeframes(data)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(stereo_isolation),
                '-c:a', 'libmp3lame', '-b:a', '192k',
                str(destination / 'sheng-mp3-stereo-isolation.mp3')], check=True)
java = rom / 'prebuilts/jdk/jdk21/linux-x86/bin'
classes = output / 'classes'
dex = output / 'dex'
classes.mkdir(exist_ok=True)
dex.mkdir(exist_ok=True)
environment = dict(os.environ, LANG='C.UTF-8', LC_ALL='C.UTF-8')
subprocess.run([str(java / 'javac'), '-source', '8', '-target', '8', '-classpath',
                str(rom / 'prebuilts/sdk/current/public/android.jar'), '-d', str(classes),
                str(workspace / 'scripts/ShengOffloadMediaProbe.java')], env=environment, check=True)
subprocess.run([str(java / 'java'), '-cp', str(rom / 'out/host/linux-x86/framework/d8.jar'),
                'com.android.tools.r8.D8', '--lib', str(rom / 'prebuilts/sdk/current/public/android.jar'),
                '--min-api', '35', '--output', str(dex),
                *map(str, classes.glob('ShengOffloadMediaProbe*.class'))],
               env=environment, check=True)
subprocess.run([str(java / 'jar'), 'cf', str(destination / 'sheng-offload-media-probe.jar'),
                '-C', str(dex), 'classes.dex'], env=environment, check=True)
print('Generated AAC stereo, MP3 mono and MediaPlayer probe.')
