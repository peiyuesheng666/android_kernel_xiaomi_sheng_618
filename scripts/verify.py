#!/usr/bin/env python3
"""Verify source provenance, release module paths, and any completed build."""
import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import subprocess

project = Path(os.environ['PROJECT_ROOT']).resolve()
root = Path(os.environ['BUILD_ROOT']).resolve()
k = root / 'k618'
expected = json.loads((project / 'provenance/source-files.json').read_text())
generated_metadata = {}
for name, want in expected.items():
    with (root / name).open('rb') as stream:
        got = hashlib.file_digest(stream, 'sha256').hexdigest()
    if got != want:
        # Camera Kbuild regenerates only these three build-identity defines.
        if name == 'k618/vendor/qcom/opensource/camera-kernel/cam_generated_h':
            text = (root / name).read_text()
            pattern = ''.join('#define CAMERA_COMPILE_' + key + ' "[^"\\n]*"\\n'
                              for key in ('TIME', 'BY', 'HOST'))
            assert re.fullmatch(pattern, text), 'Unexpected generated camera header content'
            generated_metadata[name] = {'snapshot_sha256': want, 'compiled_sha256': got}
        else:
            raise SystemExit('Source mismatch: ' + name)
mapping = json.loads((project / 'profiles/module-sources.json').read_text())
assert len(mapping) == 344
for name, relative in mapping.items():
    if relative.startswith('out/'):
        continue
    assert (k / relative).parent.is_dir(), (name, relative)
for name in ('Makefile', 'arch', 'drivers', 'fs', 'include'):
    assert (k / 'ws/common' / name).exists(), name
for path in k.rglob('*'):
    if path.is_symlink():
        assert path.resolve().is_relative_to(root), path
for path in [*project.glob('*.sh'), *(project / 'scripts').glob('*.sh')]:
    subprocess.run(['bash', '-n', path], check=True)
for path in [*(project / 'scripts').glob('*.py'), *(project / 'kernel-6.18').glob('*.py')]:
    compile(path.read_text(), str(path), 'exec')
result = {'source_files_verified': len(expected), 'module_count': len(mapping),
          'defconfig': 'sheng_defconfig',
          'stage_scripts': ['buildkernel.sh', 'buildmodules.sh', 'embed.sh', 'mkbootimage.sh'],
          'source_layout_verified': True, 'build_root': str(root), 'fresh_build_verified': False,
          'regenerated_camera_build_metadata': generated_metadata}
built = k / 'out-gki/build-result.json'
if built.exists():
    build = json.loads(built.read_text())
    for name, want in build['artifacts'].items():
        with (k / 'out-gki' / name).open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == want, name
    with (k / 'out-gki/Image').open('rb') as stream:
        header = stream.read(64)
    assert header[56:60] == b'ARM\x64', 'Invalid ARM64 Image header'
    if build['boot_packaged']:
        unpack = k / 'out-gki/boot-readback'
        subprocess.check_output([os.environ['PYTHON'], project / 'tools/mkbootimg/unpack_bootimg.py',
                                 '--boot_img', k / 'out-gki/boot.img', '--out', unpack])
        assert (unpack / 'ramdisk').stat().st_size == 0
        assert gzip.decompress((unpack / 'kernel').read_bytes()) == (k / 'out-gki/Image').read_bytes()
    abi = subprocess.check_output([os.environ['PYTHON'], project / 'tools/verify-module-abi.py',
                                   k / 'out-gki', k / 'out-gki/layer/lib/modules'], text=True)
    result.update(fresh_build_verified=True, build=build, module_abi=json.loads(abi))
else:
    result['build_status'] = 'No completed build in this prepared workspace'
dest = project / 'dist' / os.environ['TAG']
dest.mkdir(parents=True, exist_ok=True)
(dest / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
