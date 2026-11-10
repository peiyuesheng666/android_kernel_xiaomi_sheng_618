#!/usr/bin/env python3
"""Apply the small, hash-checked path fixes needed by a portable source snapshot."""
import hashlib
import json
import os
from pathlib import Path
import sys

project = Path(os.environ.get('PROJECT_ROOT', Path(__file__).resolve().parents[1]))
root = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ['BUILD_ROOT']).resolve()
for change in json.loads((project / 'provenance/relocations.json').read_text()):
    path = root / change['path']
    assert path.resolve().is_relative_to(root), path
    data = path.read_text()
    current = hashlib.sha256(path.read_bytes()).hexdigest()
    if current == change['after_sha256']:
        continue
    assert current == change['before_sha256'], path
    assert data.count(change['old']) == 1, path
    path.write_text(data.replace(change['old'], change['new']))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == change['after_sha256'], path
