#!/usr/bin/env python3
"""Keep Cirrus kernel internals out of the exported userspace header."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

work = Path(__file__).resolve().parents[1]
rom = Path('/root/sheng-lineage/lineage-24.0')
relative = 'kernel/xiaomi/sm8550-modules/qcom/opensource/audio-kernel/include/uapi/audio/sound/cs35l41.h'
file = rom / relative
repository = rom / 'kernel/xiaomi/sm8550-modules'
original = subprocess.check_output(['git', '-C', str(repository), 'show',
    'HEAD:' + str(file.relative_to(repository))], text=True)
start = '#define __CS35L41_H\n'
end = '#endif /* __CS35L41_H */'
assert original.count(start) == original.count(end) == 1
assert '#ifdef __KERNEL__' not in original
updated = original.replace(start, start + '\n/* Platform data and driver state are kernel-only, not a userspace ABI. */\n#ifdef __KERNEL__\n')
updated = updated.replace(end, '#endif /* __KERNEL__ */\n\n' + end)
assert file.read_text() in (original, updated), 'Unexpected source changes; review before patching'
if file.read_text() != updated:
    file.write_text(updated)
patch = ''.join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True),
                                    fromfile='a/' + relative, tofile='b/' + relative))
(work / 'patches/cs35l41-kernel-private-uapi.patch').write_text(patch)

clang_versions = rom / 'prebuilts/clang/host/linux-x86'
clang = sorted(p / 'bin/clang' for p in clang_versions.glob('clang-r*') if (p / 'bin/clang').is_file())[-1]
with tempfile.TemporaryDirectory(prefix='sheng-uapi-check-') as temporary:
    directory = Path(temporary)
    before = directory / 'before.h'
    before.write_text(original)
    preprocessing = [str(clang), '-E', '-P', '-D__KERNEL__', '-x', 'c']
    assert subprocess.check_output(preprocessing + [str(before)]) == subprocess.check_output(preprocessing + [str(file)]), 'Kernel declarations changed'
    exported = directory / 'cs35l41.h'
    kernel_out = rom / 'out/target/product/sheng/obj/KERNEL_OBJ'
    assert (kernel_out / 'scripts/unifdef').is_file()
    subprocess.run(['sh', str(rom / 'kernel/xiaomi/sm8550/scripts/headers_install.sh'), str(file), str(exported)], cwd=kernel_out, check=True)
    subprocess.run([str(clang), '-std=c90', '-Wall', '-Werror=implicit-function-declaration',
                    '-S', '-o', '/dev/null', '-x', 'c', '/dev/null',
                    '-include', str(exported), '-include', str(exported)], check=True)

report = {'source': relative, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
          'kernel_preprocessed_declarations_unchanged': True,
          'real_headers_install_passed': True, 'exported_header_c90_double_include_passed': True,
          'header_checks_disabled': False}
(work / 'reports/audio-private-uapi-fix.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
