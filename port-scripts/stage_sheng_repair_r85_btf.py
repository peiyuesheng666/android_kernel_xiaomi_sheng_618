#!/usr/bin/env python3
"""Make all r85 module BTF resilient to final embedded-kernel type-ID changes."""
from pathlib import Path
import json
import shutil

workspace=Path(__file__).resolve().parents[1]
project=Path('/root/sheng-618-repair-r85-project')
build=Path('/root/sheng-618-repair-r85-build')
for source,target in [('sheng_btf_distill.c','tools/sheng-btf-distill.c'),
                      ('sheng_module_btf.py','tools/module-btf.py')]:
    shutil.copyfile(workspace/'scripts'/source,project/target)
path=project/'scripts/verify.sh'
path.write_text(path.read_text().replace('/project-env.sh"','/build-env.sh"'))
path=project/'buildmodules.sh';text=path.read_text()
anchor='run gki-modules "${make_cmd[@]}" modules'
assert text.count(anchor)==1
if 'kernel-module-base.btf' not in text:
    text=text.replace(anchor,anchor+'\n"$PYTHON" "$PROJECT_ROOT/tools/module-btf.py" extract --kernel "$output/vmlinux" --output "$output/kernel-module-base.btf"')
    path.write_text(text)
path=project/'embed.sh';text=path.read_text()
anchor='[ "$(find "$modules" -maxdepth 1 -name \'*.ko\' | wc -l)" = 344 ] || { echo \'Unexpected module count\'; exit 1; }'
assert text.count(anchor)==1
if 'module-btf-distill' not in text:
    insertion='''
host_btf=$BUILD_ROOT/host-tools/btf-distill
mkdir -p "$host_btf/libbpf"
run host-libbpf make -C "$ack/tools/lib/bpf" OUTPUT="$host_btf/libbpf/" -j"$JOBS" BUILD_STATIC_ONLY=1 EXTRA_CFLAGS=-O2
gcc -O2 -Wall -Wextra -Werror -I"$ack/tools/lib/bpf" -I"$ack/tools/include/uapi" \\
  "$PROJECT_ROOT/tools/sheng-btf-distill.c" "$host_btf/libbpf/libbpf.a" -lelf -lz -o "$host_btf/sheng-btf-distill"
run module-btf-distill "$PYTHON" "$PROJECT_ROOT/tools/module-btf.py" distill --count 344 \\
  --kernel "$output/kernel-module-base.btf" --modules "$modules" --tool "$host_btf/sheng-btf-distill" \\
  --objcopy "$clang/llvm-objcopy" --output "$output/module-btf-distill.json"
'''
    text=text.replace(anchor,anchor+insertion)
    anchor='cp "$output/arch/arm64/boot/Image" "$output/Image"'
    assert text.count(anchor)==1
    text=text.replace(anchor,anchor+'''
"$PYTHON" "$PROJECT_ROOT/tools/module-btf.py" extract --kernel "$output/vmlinux" --output "$output/kernel-final-r85.btf"
run module-btf-final "$PYTHON" "$PROJECT_ROOT/tools/module-btf.py" verify --count 344 \\
  --kernel "$output/kernel-final-r85.btf" --modules "$modules" --tool "$host_btf/sheng-btf-distill" \\
  --output "$output/module-btf-final.json"
''')
    path.write_text(text)
# Drop only mapped built binaries to force external-module BTF regeneration.
# Their old .ko timestamps otherwise leave modules tied to several earlier kernels.
mapping=json.loads((project/'profiles/module-sources.json').read_text());assert len(mapping)==344
for relative in mapping.values():
    path=build/'k618'/('out-gki/'+relative[4:] if relative.startswith('out/') else relative)
    assert path.resolve().is_relative_to(build.resolve()) and path.suffix=='.ko'
    if path.exists():path.unlink()
for script in ('stage_sheng_repair_r85_btf.py','verify_sheng_repair_r85_btf.py','package_sheng_repair_r85.py'):
    shutil.copyfile(workspace/'scripts'/script,project/'port-scripts'/script)
print('Staged reproducible BTF distillation and final-kernel checks; removed 344 mapped build binaries only',flush=True)
