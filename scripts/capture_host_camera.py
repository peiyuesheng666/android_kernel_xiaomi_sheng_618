#!/usr/bin/env python3
"""Take one authorized host-camera image and release it, with a hard timeout."""
from pathlib import Path
import subprocess
import sys
import time

workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace / 'tools/camera-python'))

if len(sys.argv) > 1 and sys.argv[1] == '--worker':
    import cv2
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    try:
        if not cap.isOpened():
            raise RuntimeError('Integrated camera could not be opened')
        deadline = time.monotonic() + 6
        frame = None
        while time.monotonic() < deadline:
            ok, sample = cap.read()
            if ok:
                frame = sample
                time.sleep(0.1)
                if time.monotonic() > deadline - 4:
                    break
        if frame is None:
            raise RuntimeError('No camera frame received')
        success, encoded = cv2.imencode('.jpg', frame)
        assert success
        Path(sys.argv[2]).write_bytes(encoded.tobytes())
        print('Single frame saved; camera released in finally.')
    finally:
        cap.release()
else:
    assert len(sys.argv) == 2, 'Specify the output image path'
    subprocess.run([sys.executable, __file__, '--worker', sys.argv[1]], timeout=12, check=True)
