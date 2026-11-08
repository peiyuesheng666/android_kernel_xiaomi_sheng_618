#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Port official sheng battery-manager utilities to 6.18 in an isolated directory."""
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_kernel618_clock_port import replace_once


def main():
    project = Path(__file__).resolve().parents[1]
    plan = json.loads((project / 'device/xiaomi/sheng/interfaces/kernel/6.18/source-plan.json').read_text())
    spec = next(x for x in plan['supplemental_board_sources'] if x['name'] == 'micode-kernel')
    root = Path(plan['build_root'])
    source = root / 'src/micode-kernel'
    stage = root / 'ports/pogo'
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    assert revision == spec['revision']
    assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True)
    receipt = stage / 'source-receipt.json'
    if stage.exists() and any(stage.iterdir()):
        previous = json.loads(receipt.read_text())
        for name, sha in previous['generated_sha256'].items():
            assert hashlib.sha256((stage / name).read_bytes()).hexdigest() == sha, name
    stage.mkdir(parents=True, exist_ok=True)
    records, hashes = [], {}
    files = [(f'drivers/power/supply/pogoChg/utils/{name}.c', f'{name}.c')
             for name in ('battmngr_voter', 'battmngr_notifier', 'platform_class')]
    files += [(p.relative_to(source).as_posix(), p.relative_to(source).as_posix())
              for p in sorted((source / 'include/linux/battmngr').glob('*.h'))]
    for original, name in files:
        data = (source / original).read_bytes()
        text = data.decode().replace('\r\n', '\n')
        if name == 'platform_class.c':
            text = replace_once(text, 'class_create(THIS_MODULE, "Battmngr_class")',
                                'class_create("Battmngr_class")')
            text = replace_once(text, 'void battmngr_class_exit(void)',
                                'static void battmngr_class_exit(void)')
            text = replace_once(text, 'int battmngr_class_init(void)',
                                'static int battmngr_class_init(void)')
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
        records.append({'repository': spec['url'], 'revision': revision, 'path': original,
                        'source_sha256': hashlib.sha256(data).hexdigest(),
                        'staged_path': name, 'staged_sha256': hashes[name]})
    kbuild = ('# SPDX-License-Identifier: GPL-2.0-only\n'
              'ccflags-y += -I$(src)/include\n'
              'obj-m += xm_utils.o\n'
              'xm_utils-y := battmngr_voter.o battmngr_notifier.o platform_class.o\n')
    (stage / 'Kbuild').write_text(kbuild)
    hashes['Kbuild'] = hashlib.sha256(kbuild.encode()).hexdigest()
    receipt.write_text(json.dumps({'schema': 1, 'source_files': records, 'generated_sha256': hashes,
                                  'scope': 'battery manager notifier, voting and device class only',
                                  'charging_driver_complete': False, 'runtime_validated': False}, indent=2) + '\n')
    print(json.dumps({'stage': str(stage), 'source_files': len(records), 'runtime_validated': False}))


if __name__ == '__main__':
    main()
