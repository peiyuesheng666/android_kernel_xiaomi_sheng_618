#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage the LOS Kalama TCSR controller against ACK helpers, without editing inputs."""
import hashlib
import json
from pathlib import Path
import subprocess


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Port context changed: {old!r}')
    return text.replace(old, new, 1)


def main():
    project = Path(__file__).resolve().parents[1]
    plan = json.loads((project / 'device/xiaomi/sheng/interfaces/kernel/6.18/source-plan.json').read_text())
    root = Path(plan['build_root'])
    stage = root / 'ports/clock'
    ack = root / 'src/ack'
    los = root / 'src/lineage-kernel'
    los_spec = next(x for x in plan['board_sources'] if x['name'] == 'lineage-kernel')
    for repo, revision in ((ack, plan['kernel_core']['revision']), (los, los_spec['revision'])):
        if git(repo, 'rev-parse', 'HEAD') != revision or git(repo, 'status', '--porcelain'):
            raise ValueError(f'Input is not the clean pinned source: {repo}')
    receipt = stage / 'source-receipt.json'
    if stage.exists() and any(stage.iterdir()):
        previous = json.loads(receipt.read_text())
        for name, sha in previous['generated_sha256'].items():
            if digest((stage / name).read_bytes()) != sha:
                raise ValueError(f'Refuse to overwrite edited staged source: {name}')
    stage.mkdir(parents=True, exist_ok=True)
    sources, generated = [], {}

    def write(name, data, repo=None, original=None):
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        generated[name] = digest(data)
        if repo:
            sources.append({'repository': str(repo), 'revision': git(repo, 'rev-parse', 'HEAD'),
                            'path': original, 'source_sha256': digest((repo / original).read_bytes()),
                            'staged_path': name, 'staged_sha256': digest(data)})

    # ACK's common clock code is unmodified. Keep it in a separate module so
    # all later controllers can use one provider, rather than duplicating exports.
    helper_dir = 'drivers/clk/qcom'
    helper_names = ['common', 'clk-regmap', 'clk-alpha-pll', 'clk-pll', 'clk-rcg',
                    'clk-rcg2', 'clk-branch', 'clk-regmap-divider', 'clk-regmap-mux',
                    'clk-regmap-mux-div', 'clk-regmap-phy-mux', 'clk-hfpll', 'reset', 'gdsc']
    for name in helper_names:
        path = f'{helper_dir}/{name}.c'
        write(f'{name}.c', (ack / path).read_bytes(), ack, path)
    for header in sorted((ack / helper_dir).glob('*.h')):
        path = header.relative_to(ack).as_posix()
        write(header.name, header.read_bytes(), ack, path)

    path = 'drivers/clk/qcom/tcsrcc-kalama.c'
    text = (los / path).read_text()
    text = replace_once(text, '#include "clk-pm.h"\n', '')
    text = replace_once(text, '#include "vdd-level.h"\n', '#include <linux/platform_device.h>\n')
    text = replace_once(text, 'qcom_cc_really_probe(pdev,', 'qcom_cc_really_probe(&pdev->dev,')
    text = replace_once(text, '\tret = register_qcom_clks_pm(pdev, false, &tcsr_cc_kalama_desc);\n'
                        '\tif (ret)\n\t\tdev_err(&pdev->dev, "Failed to register for pm ops\\n");\n\n', '')
    text = replace_once(text, '\tqcom_cc_sync_state(dev, &tcsr_cc_kalama_desc);',
                        '\t/* This descriptor has no voltage proxy votes to release. */\n\tclk_sync_state(dev);')
    # Downstream's non-runtime PM path restores all clock context on hibernation.
    # TCSR has no CLK_IS_CRITICAL clocks and no regulator descriptors. The
    # downstream critical-clock/VDD extensions therefore do not apply here.
    pm = ('static int tcsr_cc_kalama_restore_early(struct device *dev)\n{\n'
          '\tclk_restore_context();\n\treturn 0;\n}\n\n'
          'static const struct dev_pm_ops tcsr_cc_kalama_pm_ops = {\n'
          '\t.restore_early = tcsr_cc_kalama_restore_early,\n};\n\n')
    text = replace_once(text, 'static struct platform_driver tcsr_cc_kalama_driver = {',
                        pm + 'static struct platform_driver tcsr_cc_kalama_driver = {')
    text = replace_once(text, '\t\t.name = "tcsr_cc-kalama",',
                        '\t\t.name = "tcsr_cc-kalama",\n\t\t.pm = &tcsr_cc_kalama_pm_ops,')
    write('tcsrcc-kalama.c', text.encode(), los, path)
    header = 'include/dt-bindings/clock/qcom,tcsrcc-kalama.h'
    write(header, (los / header).read_bytes(), los, header)
    kbuild = ('# SPDX-License-Identifier: GPL-2.0-only\n'
              'ccflags-y += -I$(src)/include\n'
              'obj-m += clk-qcom.o tcsrcc-kalama.o\n'
              'clk-qcom-y := ' + ' '.join(n + '.o' for n in helper_names) + '\n')
    write('Kbuild', kbuild.encode())
    result = {'schema': 1, 'scope': 'LOS TCSR Kalama port and unmodified ACK clock helpers',
              'source_files': sources, 'generated_sha256': generated,
              'preserves_downstream_binding': 'qcom,kalama-tcsrcc',
              'runtime_validated': False, 'boot_image': False,
              'limitations': ['Downstream CONFIG_DEEPSLEEP is not implemented in ACK.',
                             'Other Kalama clock controllers still require voltage/PLL framework migration.']}
    receipt.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'stage': str(stage), 'source_files': len(sources), 'runtime_validated': False}))


if __name__ == '__main__':
    main()
