#!/usr/bin/env python3
"""Materialize the standalone, reference-layout sheng project without touching build sources."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project-root', type=Path, default=Path('/root/sheng-618-project'))
args = parser.parse_args()
workspace = Path(__file__).resolve().parents[1]
project = args.project_root.resolve()
original = Path('/root/sheng-618')
reference = original / 'upstream-project'
snapshot = original / 'diagnostic/release-r70/source-export/sheng-6.18.32-release-r70-source'
source_archive = workspace / 'artifacts/sheng-6.18-release-r70/sheng-6.18.32-release-r70-source.tar.gz'
if project.exists():
    raise SystemExit('Destination already exists; choose a new project directory')
shutil.copytree(workspace / 'kernel-project', project)
for name in ('assets', 'provenance', 'patches'):
    (project / name).mkdir(exist_ok=True)
shutil.copytree(snapshot / 'configs', project / 'profiles', dirs_exist_ok=True)
shutil.copytree(snapshot / 'tools', project / 'tools', dirs_exist_ok=True)
shutil.copyfile(workspace / 'scripts/audit_kernel618_modules.py', project / 'tools/audit_kernel618_modules.py')
shutil.copytree(snapshot / 'provenance', project / 'provenance', dirs_exist_ok=True)
shutil.copytree(snapshot / 'k618/sheng-ports', project / 'kernel-6.18/sheng-ports', dirs_exist_ok=True)
for name in ('input-sources.json', 'upstreams.json', 'soc-baseline.json'):
    shutil.copyfile(reference / 'provenance' / name, project / 'provenance' / ('reference-' + name))
shutil.copytree(reference / 'patches', project / 'patches/reference', dirs_exist_ok=True)
shutil.copyfile(snapshot / 'provenance/sheng-release-cleanup.patch', project / 'patches/sheng-release-cleanup.patch')
shutil.copyfile(workspace / 'reports/kernel618-release-r70-hardware.json', project / 'provenance/original-r70-hardware.json')
shutil.copyfile(source_archive, project / 'assets' / source_archive.name)
with source_archive.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
assert digest == '7c054599ce763bbbd75f21dccfc77102b2fb55f3dacb3f25c2d4d4ed03cef437'
inputs = {'path': 'assets/' + source_archive.name, 'sha256': digest, 'prefix': snapshot.name,
          'mode': 'complete-adapted-release-snapshot', 'revision': 'release-r70'}
(project / 'provenance/source-cache.json').write_text(json.dumps(inputs, indent=2) + '\n')
(project / 'assets/SHA256SUMS').write_text(digest + '  ' + source_archive.name + '\n')
all_hashes = json.loads((snapshot / 'SOURCE-SHA256.json').read_text())
sources = {name: value for name, value in all_hashes.items() if name.startswith('k618/')}
relative = 'k618/sheng-ports/ps5169/Makefile'
old = '-I/root/sheng-618/upstream-build/k618/soc/include'
new = '-I$(SOC)/include'
data = (snapshot / relative).read_text()
assert data.count(old) == 1
portable = data.replace(old, new)
after_sha = hashlib.sha256(portable.encode()).hexdigest()
changes = [dict(path=relative, old=old, new=new, before_sha256=sources[relative], after_sha256=after_sha)]
(project / 'provenance/relocations.json').write_text(json.dumps(changes, indent=2) + '\n')
sources[relative] = after_sha
(project / 'kernel-6.18/sheng-ports/ps5169/Makefile').write_text(portable)
(project / 'provenance/source-files.json').write_text(json.dumps(sources, indent=2) + '\n')
modules = json.loads((project / 'profiles/module-sources.json').read_text())
(project / 'kernel-6.18/modules.tsv').write_text('module\tsource-relative-to-k618\n' +
    ''.join(name + '\t' + path + '\n' for name, path in sorted(modules.items())))
manifest = ET.parse(project / 'provenance/kernel-manifest.xml')
toolchains = [dict(p.attrib, url='https://android.googlesource.com/' + p.attrib['name'])
              for p in manifest.findall('project') if p.attrib['path'] in (
                  'prebuilts/clang/host/linux-x86', 'prebuilts/rust-toolchain/linux-x86',
                  'prebuilts/clang-tools', 'prebuilts/kernel-build-tools', 'prebuilts/build-tools')]
(project / 'provenance/toolchains.json').write_text(json.dumps(toolchains, indent=2) + '\n')
for path in project.rglob('*'):
    if path.is_file() and path.suffix in ('.sh', '.py', '.md', '.json', '.env', '.tsv'):
        data = path.read_bytes()
        if b'\r\n' in data:
            path.write_bytes(data.replace(b'\r\n', b'\n'))
    if path.suffix == '.sh':
        path.chmod(0o755)
for path in project.rglob('*.sh'):
    subprocess.run(['bash', '-n', path], check=True)
report = {'project_root': str(project), 'reference_revision': 'c3956156ce7c4193c451dfda531fad72d35bfebb',
          'reference_layout_adopted': True, 'kernel_module_build_language': 'Bash',
          'module_count': len(modules), 'source_files': len(sources), 'source_cache_sha256': digest,
          'fresh_build_verified': False, 'new_hardware_validation': False}
(workspace / 'reports/kernel618-reference-layout.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
