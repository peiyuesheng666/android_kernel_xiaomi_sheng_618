#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproducible external-driver staging and the shared ACK 6.18 build environment."""
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess

PROJECT = Path(__file__).resolve().parents[1]
PLAN = json.loads((PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/source-plan.json').read_text())
ROOT = Path(PLAN['build_root'])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


class Port:
    def __init__(self, name):
        self.name = name
        self.stage = ROOT / 'ports' / name
        self.receipt = self.stage / 'source-receipt.json'
        if self.stage.exists() and any(self.stage.iterdir()):
            old = json.loads(self.receipt.read_text())
            for path, expected in old['generated_sha256'].items():
                if sha((self.stage / path).read_bytes()) != expected:
                    raise ValueError(f'Refuse to overwrite edited staged source: {self.stage / path}')
        self.stage.mkdir(parents=True, exist_ok=True)
        self.records, self.hashes, self.checked, self.pending = [], {}, set(), {}

    def check_source(self, name):
        repo = ROOT / 'src' / name
        spec = PLAN['kernel_core'] if name == 'ack' else next(
            s for s in PLAN['board_sources'] + PLAN.get('supplemental_board_sources', []) if s['name'] == name)
        if name not in self.checked:
            if git(repo, 'rev-parse', 'HEAD') != spec['revision'] or git(repo, 'status', '--porcelain'):
                raise ValueError(f'Input is not the clean pinned source: {repo}')
            self.checked.add(name)
        return repo, spec

    def write(self, name, data):
        if isinstance(data, str):
            data = data.encode()
        self.pending[name] = data
        self.hashes[name] = sha(data)

    def copy(self, source, original, name=None, transform=None):
        repo, spec = self.check_source(source)
        data = (repo / original).read_bytes()
        staged = transform(data.decode().replace('\r\n', '\n')).encode() if transform else data
        name = name or original
        self.write(name, staged)
        self.records.append({'repository': spec['url'], 'revision': spec['revision'], 'path': original,
                             'source_sha256': sha(data), 'staged_path': name, 'staged_sha256': sha(staged)})

    def finish(self, modules, limits=()):
        # Generate everything before touching the previous build's staged inputs.
        # A failed transformation must leave its previous receipt reproducible.
        for name, data in self.pending.items():
            target = self.stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.receipt.write_text(json.dumps({'schema': 1, 'source_files': self.records,
            'generated_sha256': self.hashes, 'modules': modules, 'runtime_validated': False,
            'limits': list(limits)}, indent=2) + '\n')

    def build(self, dependencies=(), keep_going=True):
        if (ROOT / 'logs/build-status.txt').read_text().strip() != 'complete':
            raise ValueError('Build the pinned ACK baseline first')
        sdk = Path('/root/sheng-lineage/lineage-24.0/prebuilts')
        clang = sdk / 'clang/host/linux-x86/clang-r584948b'
        rust = sdk / 'rust-toolchain/linux-x86/1.91.1'
        elfutils = ROOT / 'host-tools/elfutils-0.193'
        env = {**os.environ, 'PATH': ':'.join(map(str, (clang / 'bin', rust / 'bin',
               sdk / 'clang-tools/linux-x86/bin', sdk / 'kernel-build-tools/linux_musl-x86/bin'))) + ':/usr/bin:/bin',
               'LIBCLANG_PATH': str(clang / 'lib'), 'RUSTC_BOOTSTRAP': '1',
               'KBUILD_GENDWARFKSYMS_STABLE': '1', 'RUST_LIB_SRC': str(rust / 'lib/rustlib/src/rust/library')}
        command = ['make', '-C', str(ROOT / 'src/ack'), 'O=' + str(ROOT / 'out/ack-arm64'),
                   'M=' + str(self.stage), 'ARCH=arm64', 'LLVM=1', 'LLVM_IAS=1',
                   '-j' + os.environ.get('JOBS', '24'),
                   f'HOSTCFLAGS=-O2 -I{elfutils}/include', f'HOSTLDFLAGS=-L{elfutils}/lib -Wl,-rpath,{elfutils}/lib',
                   f'RUSTC={rust}/bin/rustc', f'HOSTRUSTC={rust}/bin/rustc',
                   f'BINDGEN={sdk}/clang-tools/linux-x86/bin/bindgen',
                   f'PAHOLE={sdk}/kernel-build-tools/linux_musl-x86/bin/pahole',
                   'KCFLAGS=-D__ANDROID_COMMON_KERNEL__', 'LOCALVERSION=-android17-5-sheng-ack-baseline']
        if keep_going:
            command.append('-k')
        if dependencies:
            command.append('KBUILD_EXTRA_SYMBOLS=' + ' '.join(str(ROOT / 'ports' / d / 'Module.symvers')
                                                             for d in dependencies))
        command.append('modules')
        log = ROOT / 'logs' / f'build-{self.name}-port.log'
        with log.open('w') as stream:
            result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT)
        receipt = json.loads(self.receipt.read_text())
        status = {'exit_code': result.returncode, 'log': str(log), 'dependencies': list(dependencies),
                  'modules': {name: sha((self.stage / name).read_bytes()) for name in receipt['modules']
                              if not result.returncode and (self.stage / name).exists()},
                  'source_receipt_sha256': sha(self.receipt.read_bytes()), 'runtime_validated': False}
        (self.stage / 'build-result.json').write_text(json.dumps(status, indent=2) + '\n')
        print(json.dumps({'port': self.name, **status}), flush=True)
        if result.returncode:
            lines = log.read_text().splitlines()
            errors = [line for line in lines if 'error:' in line or 'ERROR:' in line or 'warning:' in line]
            print('\n'.join(errors[:100] or lines[-35:]), flush=True)
        return result.returncode


def replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError(f'Port context changed ({text.count(old)} != {count}): {old!r}')
    return text.replace(old, new)


def void_remove(text, function):
    """Migrate a remove callback only when every explicit return is zero."""
    match = re.search(r'\bint (' + re.escape(function) + r'\(struct platform_device \*\w+\)\n\{)', text)
    if not match:
        raise ValueError(f'Cannot locate remove callback {function}')
    end = text.index('\n}', match.end()) + 2
    body = text[match.end():end]
    returns = re.findall(r'\breturn\s+([^;]+);', body)
    if not returns or any(value.strip() != '0' for value in returns):
        raise ValueError(f'Remove callback has nonzero return paths: {function}: {returns}')
    return text[:match.start()] + 'void ' + match.group(1) + re.sub(r'\breturn\s+0;', 'return;', body) + text[end:]
