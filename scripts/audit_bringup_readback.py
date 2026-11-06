from pathlib import Path
import hashlib
import json
import os
import sys

def tree(root):
    result = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            result[str(path.relative_to(root))] = ('link', os.readlink(path))
        elif path.is_file():
            stat = path.stat()
            result[str(path.relative_to(root))] = ('file', hashlib.sha256(path.read_bytes()).hexdigest(),
                stat.st_uid, stat.st_gid, stat.st_mode & 0o7777)
    return result

build = Path('/root/sheng-lineage/system-bringup-r2')
partition = sys.argv[1] if len(sys.argv) > 1 else 'vendor'
before, after = tree(build / partition), tree(build / (partition + '-readback'))
differences = {key: (before.get(key), after.get(key)) for key in before.keys() | after.keys()
               if before.get(key) != after.get(key)}
print(json.dumps(differences, indent=2))
