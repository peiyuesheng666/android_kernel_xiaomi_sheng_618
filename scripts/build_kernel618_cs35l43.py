#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the official sheng CS35L43 amplifier module against the 6.18 baseline."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

from prepare_kernel618_clock_port import replace_once


def main():
    project = Path(__file__).resolve().parents[1]
    plan = json.loads((project / 'device/xiaomi/sheng/interfaces/kernel/6.18/source-plan.json').read_text())
    spec = next(x for x in plan['supplemental_board_sources'] if x['name'] == 'micode-audio')
    root = Path(plan['build_root'])
    source = root / 'src/micode-audio'
    stage = root / 'ports/cs35l43'
    assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == spec['revision']
    assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True)
    assert (root / 'logs/build-status.txt').read_text().strip() == 'complete'
    receipt = stage / 'source-receipt.json'
    if stage.exists() and any(stage.iterdir()):
        previous = json.loads(receipt.read_text())
        for name, sha in previous['generated_sha256'].items():
            assert hashlib.sha256((stage / name).read_bytes()).hexdigest() == sha, name
    stage.mkdir(parents=True, exist_ok=True)
    files = [(p.relative_to(source).as_posix(), p.name)
             for p in sorted((source / 'asoc/codecs/cs35l43').iterdir()) if p.suffix in ('.c', '.h')]
    files.append(('include/uapi/audio/sound/cs35l43.h', 'include/sound/cs35l43.h'))
    records, hashes = [], {}
    for original, name in files:
        data = (source / original).read_bytes()
        text = data.decode().replace('\r\n', '\n')
        if name == 'cs35l43-i2c.c':
            text = replace_once(text, 'static int cs35l43_i2c_probe(struct i2c_client *client,\n'
                                '\t\t\t\tconst struct i2c_device_id *id)',
                                'static int cs35l43_i2c_probe(struct i2c_client *client)')
            text = replace_once(text, 'static int cs35l43_i2c_remove(struct i2c_client *client)',
                                'static void cs35l43_i2c_remove(struct i2c_client *client)')
            text = replace_once(text, '\treturn cs35l43_remove(cs35l43);',
                                '\tcs35l43_remove(cs35l43);')
        elif name == 'wm_adsp.h':
            text = replace_once(text, 'regmap_read: %d, (0x%x, %x)', 'regmap_read: %d, (0x%x, %p)')
            for operation in ('regmap_raw_write', 'regmap_raw_write_async', 'regmap_raw_read'):
                old = f'{operation}: %d, (0x%x, %p, %d), ret = %d\\n", __i, reg, val, len, __ret);'
                new = f'{operation}: %d, (0x%x, %p, %zu), ret = %d\\n", __i, reg, val, (size_t)(len), __ret);'
                text = replace_once(text, old, new)
            text = replace_once(text, 'struct snd_compr_tstamp *tstamp', 'struct snd_compr_tstamp64 *tstamp')
        elif name == 'wm_adsp.c':
            assert text.count('asoc_rtd_to_codec(') == 5
            text = text.replace('asoc_rtd_to_codec(', 'snd_soc_rtd_to_codec(')
            text = replace_once(text, 'wm_adsp2_preloader_put: %d', 'wm_adsp2_preloader_put: %ld')
            text = replace_once(text, 'struct snd_compr_tstamp *tstamp', 'struct snd_compr_tstamp64 *tstamp')
        elif name == 'cs35l43-cal.c':
            text = replace_once(text, 'int cs35l43_apply_calibration(', 'static int cs35l43_apply_calibration(')
        elif name == 'cs35l43.c':
            assert text.count('SND_SOC_DAIFMT_CBS_CFS') == 3
            text = text.replace('SND_SOC_DAIFMT_CBS_CFS', 'SND_SOC_DAIFMT_CBC_CFC')
            text = replace_once(text, 'int cs35l43_component_write(', 'static int cs35l43_component_write(')
            text = replace_once(text, 'unsigned int cs35l43_component_read(', 'static unsigned int cs35l43_component_read(')
            text = replace_once(text, 'static struct snd_soc_dai_driver cs35l43_dai[] = {',
                                'static const struct snd_soc_dai_ops cs35l43_textlog_ops = {\n'
                                '\t.compress_new = snd_soc_new_compress,\n};\n\n'
                                'static struct snd_soc_dai_driver cs35l43_dai[] = {')
            text = replace_once(text, '\t\t.compress_new = &snd_soc_new_compress,',
                                '\t\t.ops = &cs35l43_textlog_ops,')
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
        records.append({'repository': spec['url'], 'revision': spec['revision'], 'path': original,
                        'source_sha256': hashlib.sha256(data).hexdigest(),
                        'staged_path': name, 'staged_sha256': hashes[name]})
    kbuild = ('# SPDX-License-Identifier: GPL-2.0-only\n'
              'ccflags-y += -I$(src)/include -DCONFIG_ASYNC_LOAD_FIRMWARE\n'
              'obj-m += cs35l43_dlkm.o\n'
              'cs35l43_dlkm-y := cs35l43.o cs35l43-i2c.o cs35l43-tables.o wm_adsp.o\n')
    (stage / 'Kbuild').write_text(kbuild)
    hashes['Kbuild'] = hashlib.sha256(kbuild.encode()).hexdigest()
    receipt.write_text(json.dumps({'schema': 1, 'source_files': records, 'generated_sha256': hashes,
                                  'runtime_validated': False,
                                  'limits': ['Vendor ONETRACK telemetry is not enabled; its mihw provider is not ported.']}, indent=2) + '\n')
    sdk = Path('/root/sheng-lineage/lineage-24.0/prebuilts')
    clang = sdk / 'clang/host/linux-x86/clang-r584948b'
    rust = sdk / 'rust-toolchain/linux-x86/1.91.1'
    elfutils = root / 'host-tools/elfutils-0.193'
    env = {**os.environ, 'PATH': ':'.join(map(str, (clang / 'bin', rust / 'bin',
           sdk / 'clang-tools/linux-x86/bin', sdk / 'kernel-build-tools/linux_musl-x86/bin'))) + ':/usr/bin:/bin',
           'LIBCLANG_PATH': str(clang / 'lib'), 'RUSTC_BOOTSTRAP': '1',
           'KBUILD_GENDWARFKSYMS_STABLE': '1', 'RUST_LIB_SRC': str(rust / 'lib/rustlib/src/rust/library')}
    command = ['make', '-C', str(root / 'src/ack'), 'O=' + str(root / 'out/ack-arm64'),
               'M=' + str(stage), 'ARCH=arm64', 'LLVM=1', 'LLVM_IAS=1', '-k', '-j' + str(os.cpu_count()),
               f'HOSTCFLAGS=-O2 -I{elfutils}/include', f'HOSTLDFLAGS=-L{elfutils}/lib -Wl,-rpath,{elfutils}/lib',
               f'RUSTC={rust}/bin/rustc', f'HOSTRUSTC={rust}/bin/rustc',
               f'BINDGEN={sdk}/clang-tools/linux-x86/bin/bindgen',
               f'PAHOLE={sdk}/kernel-build-tools/linux_musl-x86/bin/pahole',
               'KCFLAGS=-D__ANDROID_COMMON_KERNEL__', 'LOCALVERSION=-android17-5-sheng-ack-baseline', 'modules']
    log = root / 'logs/build-cs35l43-port.log'
    with log.open('w') as stream:
        result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT)
    print(json.dumps({'exit_code': result.returncode, 'log': str(log), 'runtime_validated': False}))
    if result.returncode:
        print('\n'.join(log.read_text().splitlines()[-80:]))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
