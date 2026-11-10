#!/usr/bin/env python3
"""Remove the retired 6.12 baseline and relocate shared input files used by 6.18."""
import hashlib
import json
from pathlib import Path
import shutil

workspace = Path(__file__).resolve().parents[1]
retired = Path('/root/sheng-612')
shared = Path('/root/sheng-source-inputs')
assert retired.resolve() == retired and not retired.is_symlink()
assert (retired.is_dir() and not shared.exists()) or (not retired.exists() and shared.is_dir())
active_swap = {line.split()[0] for line in Path('/proc/swaps').read_text().splitlines()[1:]}
assert str(retired / 'lineage-build.swap') not in active_swap, 'Old swap is still active'
busy = []
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    for link in [proc / 'cwd', proc / 'exe', *list((proc / 'fd').glob('*'))]:
        try:
            target = str(link.readlink())
        except (OSError, PermissionError):
            continue
        if target == str(retired) or target.startswith(str(retired) + '/'):
            busy.append((proc.name, target))
    try:
        if str(retired) + '/' in (proc / 'maps').read_text():
            busy.append((proc.name, 'mapped file in retired tree'))
    except (OSError, PermissionError):
        pass
assert not busy, busy

report = {'retired_root': str(retired), 'shared_input_root': str(shared),
          'relocated': [], 'deleted_wsl': [], 'deleted_workspace': [], 'updated_files': []}
shared.mkdir(exist_ok=True)
for name in ('reference', 'stock', 'tools'):
    source = retired / name
    target = shared / name
    assert source.resolve().is_relative_to(retired) and target.parent == shared
    if source.exists():
        assert not target.exists()
        shutil.move(source, target)
    else:
        assert target.is_dir()
    report['relocated'].append({'from': str(source), 'to': str(target)})
# Exact child allowlist, after verifying no process uses this retired tree.
allowed = {'src', 'toolchains', 'out', 'logs', 'lineage-build.swap'}
assert not retired.exists() or {p.name for p in retired.iterdir()} <= allowed
for path in list(retired.iterdir()) if retired.exists() else []:
    assert path.resolve().parent == retired and not path.is_symlink()
    report['deleted_wsl'].append(str(path))
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
if retired.exists():
    retired.rmdir()
else:
    report['deleted_wsl'] = [str(retired / name) for name in sorted(allowed)]

obsolete = ['scripts/build_ack.sh', 'scripts/fetch_ack.sh', 'scripts/fetch_toolchains.py',
            'scripts/export_baseline.py', 'scripts/verify_build.py', 'scripts/probe_sources.py',
            'reports/build-result.json', 'reports/toolchains.json', 'reports/source-probe.json',
            'artifacts/6.12.96-4k-android16-7-sheng-ack-baseline-baseline.tar.gz',
            'artifacts/6.12.96-4k-android16-7-sheng-ack-baseline-baseline.tar.gz.sha256']
for name in obsolete:
    path = workspace / name
    expected_parent = (workspace / Path(name).parent).resolve()
    assert path.resolve().parent == expected_parent and not path.is_symlink(), path
    if path.exists():
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        report['deleted_workspace'].append({'path': name, 'sha256': digest, 'bytes': path.stat().st_size})
        path.unlink()

paths = [workspace / 'README.md', *(workspace / 'scripts').glob('*.py'),
         *(workspace / 'scripts').glob('*.sh'),
         workspace / 'device/xiaomi/sheng/tools/build_hardware.sh',
         workspace / 'device/xiaomi/sheng/tools/extract_vendor.sh',
         workspace / 'device/xiaomi/sheng/docs/nuwa-face-reference-review-20261108.md',
         workspace / 'reports/audit-sources.json', workspace / 'reports/device-tree-provenance-audit.json',
         workspace / 'reports/stock-boot.json', workspace / 'reports/stock-ramdisk.json',
         workspace / 'reports/LINEAGE_STATUS.md']
for path in paths:
    if not path.exists() or path == Path(__file__).resolve():
        continue
    text = path.read_text(encoding='utf-8')
    updated = text.replace('/root/sheng-612/toolchains/clang-r536225/bin',
                           '/root/sheng-618-project-deps/prebuilts/clang/host/linux-x86/clang-r584948c/bin')
    updated = updated.replace('/root/sheng-612/lineage-build.swap', '/root/sheng-lineage/lineage-build.swap')
    updated = updated.replace('/root/sheng-612/reference', '/root/sheng-source-inputs/reference')
    updated = updated.replace('/root/sheng-612/stock', '/root/sheng-source-inputs/stock')
    if path.name in ('audit_stock.py', 'inventory_ramdisk.py'):
        updated = updated.replace('/root/sheng-612', '/root/sheng-source-inputs')
    if path.name == 'prepare_audit_sources.py':
        updated = updated.replace('/root/sheng-612/logs', '/root/sheng-source-inputs/logs')
    if path.name == 'inspect_environment.sh':
        updated = updated.replace('/root/sheng-612', '/root/sheng-618-project-build')
    if updated != text:
        path.write_text(updated, encoding='utf-8')
        report['updated_files'].append(path.relative_to(workspace).as_posix())
(shared / 'logs').mkdir(exist_ok=True)

(workspace / 'README.md').write_text('''# 小米平板 6S Pro · Linux 6.18.32

当前内核项目按 [小米 13 Pro 参考仓库](https://github.com/JiaqiLi404/android_kernel_618_for_sm8550)
的结构整理。设备代号 sheng，目标系统 HyperOS OS3.0.303.0.WNXCNXM。
早期 6.12 基线已退役并删除。

## 源码与构建

- [内核工程说明](kernel-project/README.zh-CN.md)
- [Bash 构建入口](kernel-project/build.sh)
- [构建与依赖](kernel-project/docs/BUILD.zh-CN.md)
- [来源与目录布局](kernel-project/docs/PROVENANCE.zh-CN.md)
- [验证说明](kernel-project/docs/VALIDATION.zh-CN.md)

WSL Ubuntu-22.04：

```text
/root/sheng-618-project                         整理后的项目
/root/sheng-618-project-build/k618/ws/common     ACK 6.18 主源码
/root/sheng-618-project-build/k618/soc           SoC 外部驱动
/root/sheng-618-project-build/k618/vendor        厂商外部驱动
/root/sheng-618-project-build/k618/sheng-ports    平板专用驱动
/root/sheng-618-project-deps                     本次验证使用的独立工具链
/root/sheng-source-inputs                       共用原厂解析与参考输入
```

```bash
cd /root/sheng-618-project
bash scripts/run-limited.sh bootstrap
export PREBUILTS=/root/sheng-618-project-deps/prebuilts
export ELFUTILS=/root/sheng-618-project-deps/elfutils-0.193
bash build.sh
bash scripts/run-limited.sh verify
```

最终文件在项目的 `dist/release-r70/`。模块采用与参考项目相同的外部编译机制，
生成 `/lib/modules` 模块层并嵌入 Image；完整 ACK 源码没有与厂商驱动强行合并。

## 测试记录

- [r70 原始发布与源码包记录](reports/kernel618-release-r70.md)
- [本次目录整理记录](reports/kernel618-reference-layout.json)
- [6.12 清理记录](reports/kernel612-cleanup.json)

原始 r70 已实机启动。本次整理后重编、刷写和硬件测试结果以新报告为准。
现有 Android 设备配置另见 [sheng 设备说明](device/xiaomi/sheng/README.md)。
''', encoding='utf-8')
(workspace / 'reports/KERNEL618_STATUS.md').write_text('''# sheng 6.18 状态

源码工程按 JiaqiLi404/android_kernel_618_for_sm8550 的目录结构整理，
目标为原厂 HyperOS OS3.0.303.0.WNXCNXM。根目录 `build.sh` 使用 Bash。

WSL 项目：`/root/sheng-618-project`。
准备后的源码：`/root/sheng-618-project-build/k618`。
6.12 基线已删除；仍在使用的原厂解析和参考输入移至 `/root/sheng-source-inputs`。

当前整理、完整重编及实机结果见 `kernel618-reference-layout.json` 和本次测试报告。
原始 r70 发布及源码包验证见 `kernel618-release-r70.md`。
历史 6.18 调试证据仍保留在各版本 JSON 与硬件报告中。
''', encoding='utf-8')
(workspace / 'reports/kernel612-cleanup.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
