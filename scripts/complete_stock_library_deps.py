#!/usr/bin/env python3
"""Complete private DT_NEEDED dependencies from the read-only stock cache."""
import json
from pathlib import Path
import re
import subprocess

WORK = Path(__file__).resolve().parents[1]
ROM = Path('/root/sheng-lineage/lineage-24.0')
DUMP = ROM.parent / 'firmware-dump/extract-source'
inventory = WORK / 'device/xiaomi/sheng/proprietary-files.txt'
lines = inventory.read_text().splitlines()
entries = {line.lstrip('-').split(';')[0].split('|')[0].split(':')[-1]: line
           for line in lines if line and not line.startswith('#')}
providers = set()
for relative in (ROM / 'out/.module_paths/Android.bp.list').read_text().splitlines():
    if relative.startswith('vendor/xiaomi/') or relative.startswith('device/') and not relative.startswith('device/xiaomi/sheng/'):
        continue
    if relative.startswith('hardware/qcom/'):
        continue  # Interfaces from older GPS SoCs do not satisfy this board's namespace.
    if relative.startswith('hardware/qcom-caf/') and not relative.startswith(('hardware/qcom-caf/sm8550/', 'hardware/qcom-caf/common/', 'hardware/qcom-caf/wlan/')):
        continue
    file = ROM / relative
    if file.is_file():
        text = file.read_text()
        providers.update(re.findall(r'\bname\s*:\s*"([^"$]+)"', text))
        if relative.startswith('hardware/lineage/compat/'):
            providers.update(re.findall(r'\bstem\s*:\s*"([^"$]+)"', text))

queue = []
for destination, line in entries.items():
    source = line.lstrip('-').split(';')[0].split('|')[0].split(':')[0]
    if not re.match(r'^(?:vendor|odm|system_ext|system)/(?:lib|lib64|bin)/', source):
        continue
    file = DUMP / source
    if file.is_file():
        with file.open('rb') as stream:
            header = stream.read(20)
        if header[:4] == b'\x7fELF' and int.from_bytes(header[18:20], 'little') in (40, 183):
            queue.append((source, 'lib64' if header[4] == 2 else 'lib'))
known = {Path(path).stem for path in entries if path.endswith('.so')}
added, unresolved, visited = [], [], set()
while queue:
    source, arch = queue.pop()
    if source in visited:
        continue
    visited.add(source)
    dynamic = subprocess.check_output(['/root/sheng-618-project-deps/prebuilts/clang/host/linux-x86/clang-r584948c/bin/llvm-readelf',
                                       '-d', str(DUMP / source)], text=True)
    for dependency in re.findall(r'\(NEEDED\).*\[([^\]]+)\]', dynamic):
        module = dependency.removesuffix('.so')
        aidl = re.fullmatch(r'(.+)-V\d+-(?:ndk|cpp)', module)
        if module in known or module in providers or aidl and aidl[1] in providers:
            continue
        if dependency.startswith(('android.', 'libclang_rt.')):
            continue
        candidates = [f'{partition}/{arch}/{dependency}' for partition in ('vendor', 'odm', 'system_ext')]
        candidate = next((name for name in candidates if (DUMP / name).is_file()), None)
        if candidate is None:
            unresolved.append({'consumer': source, 'needed': dependency})
            continue
        entries[candidate] = candidate
        known.add(module)
        added.append({'path': candidate, 'consumer': source, 'needed': dependency})
        queue.append((candidate, arch))
inventory.write_text('# Standalone sheng stock inventory with source-provided interfaces and resolved private dependencies.\n'
                     + '\n'.join(entries[key] for key in sorted(entries)) + '\n')
report_path = WORK / 'reports/stock-library-dependency-closure.json'
previous = json.loads(report_path.read_text())['added'] if report_path.exists() else []
report = {'added': previous + added, 'unresolved': unresolved, 'elf_inputs_inspected': len(visited),
          'elf_abi_checks_disabled': False}
report_path.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'added': added, 'unresolved_count': len(unresolved), 'elf_inputs_inspected': len(visited)}, indent=2))
