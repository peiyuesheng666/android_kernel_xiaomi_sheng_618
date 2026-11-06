#!/usr/bin/env python3
"""Wait for the asynchronous stock KGSL probe before initializing gralloc."""
from pathlib import Path
import subprocess

workspace = Path(__file__).resolve().parents[1]
display = Path('/root/sheng-lineage/lineage-24.0/hardware/qcom-caf/sm8550/display')
source = display / 'gralloc/gr_adreno_info.cpp'
text = source.read_text()
old = '''  fstream fs(kgsl_path, fstream::in);
  if (!fs.is_open()) {
    return;
  }
'''
new = '''  fstream fs(kgsl_path, fstream::in);
  // KGSL probes asynchronously. Caching an uninitialized singleton before
  // /dev/kgsl-3d0 exists makes allocation and import disagree on RGB stride.
  for (int attempt = 0; !fs.is_open() && attempt < 100; ++attempt) {
    usleep(100000);
    fs.clear();
    fs.open(kgsl_path, fstream::in);
  }
  if (!fs.is_open()) {
    ALOGE("KGSL did not become available within 10 seconds");
    return;
  }
'''
if new not in text:
    assert text.count(old) == 1
    text = text.replace(old, new)
    text = text.replace('#include <fstream>\n', '#include <fstream>\n#include <unistd.h>\n')
    source.write_text(text)
diff = subprocess.run(['git', '-C', str(display), 'diff', '--', 'gralloc/gr_adreno_info.cpp'],
                      check=True, capture_output=True).stdout
(workspace / 'patches/gralloc-wait-for-kgsl.patch').write_bytes(diff)
print('Saved the repeatable KGSL initialization patch.')
