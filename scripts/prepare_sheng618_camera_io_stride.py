#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restore VFE780's supplied plane stride after an observed FD DMA overrun."""
import difflib
import hashlib
import json
import re
import subprocess
from build_sheng618_upstream import K618, PROJECT, ROOT

prefix = 'vendor/qcom/opensource/camera-kernel/'
vfe = 'drivers/cam_isp/isp_hw_mgr/isp_hw/vfe_hw/'
names = [vfe + 'vfe_bus/cam_vfe_bus_ver3.c',
         vfe + 'vfe_bus/cam_vfe_bus_ver3.h', vfe + 'vfe17x/cam_vfe780.h']
receipt = PROJECT / 'reports/kernel618-camera-io-stride-source.json'
prior = json.loads(receipt.read_text()) if receipt.exists() else None
backup = ROOT / 'diagnostic/hardware-r37/camera-stride-before'
sha = lambda data: hashlib.sha256(data).hexdigest()

references = [
    ('LineageOS-sm8550-modules', ROOT / 'src/lineage-modules',
     '92a9fde479d3262da080cfd28bab0775b0da500a', 'qcom/opensource/camera-kernel/'),
    ('MiCode-sheng-camera', ROOT / 'src/micode-camera',
     'ad342a26a37e9fabc2f626a6622b788bf9aa546b', '')]
reference_records = []
for name, repo, commit, subdir in references:
    assert subprocess.check_output(['git', '-C', repo, 'rev-parse', 'HEAD'], text=True).strip() == commit
    path = repo / subdir / names[0]
    text = path.read_text()
    assert re.search(r'wm_data->hw_regs->image_cfg_2,\s*stride\);', text)
    reference_records.append(dict(repository=name, commit=commit, file=subdir + names[0],
                                  sha256=sha(path.read_bytes()),
                                  applicability='Program raw IO stride; alignment was used only for cached comparison'))

changes = {
    names[0]: [
        ('\t\tif (cfg->stride != 0)\n\t\t\tval = cfg->stride;\n',
         '\t\t/* VFE780 accepts the supplied plane pitch, including FD NV12\n'
         '\t\t * pitch 852. Rounding it changes the DMA layout and can write\n'
         '\t\t * past the mapped allocation. Retain explicit WM overrides.\n'
         '\t\t */\n'
         '\t\tif (cfg->stride != 0)\n\t\t\tval = cfg->stride;\n'
         '\t\telse if (bus_priv->bus_hw_info->use_io_stride)\n\t\t\tval = stride;\n'),
        ('\tbus_priv->bus_hw_info = ver3_hw_info;\n',
         '\tbus_priv->bus_hw_info = ver3_hw_info;\n'
         '\tif (ver3_hw_info->use_io_stride)\n'
         '\t\tCAM_INFO(CAM_ISP, "VFE:%u VFE780 supplied plane stride enabled",\n'
         '\t\t\tsoc_info->index);\n')],
    names[1]: [
        (' * @support_dyn_offset:              Flag for supporting dynamic offset\n',
         ' * @support_dyn_offset:              Flag for supporting dynamic offset\n'
         ' * @use_io_stride:                   Program supplied plane pitch without rounding\n'),
        ('\tbool     support_dyn_offset;\n',
         '\tbool     support_dyn_offset;\n\tbool     use_io_stride;\n')],
    names[2]: [
        ('static struct cam_vfe_bus_ver3_hw_info vfe780_bus_hw_info = {\n',
         'static struct cam_vfe_bus_ver3_hw_info vfe780_bus_hw_info = {\n'
         '\t.use_io_stride = true,\n')]
}
files, patch = {}, []
for name in names:
    path = K618 / prefix / name
    saved = backup / name
    current = path.read_bytes()
    if not saved.exists():
        assert prior is None, 'Missing immutable baseline'
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(current)
    before = saved.read_bytes()
    assert current == before or (prior and sha(current) == prior['files'][prefix + name]['after'])
    text = before.decode()
    for old, new in changes[name]:
        assert text.count(old) == 1, (name, old)
        text = text.replace(old, new, 1)
    path.write_text(text)
    files[prefix + name] = dict(before=sha(before), after=sha(path.read_bytes()))
    patch.extend(difflib.unified_diff(before.decode().splitlines(True), text.splitlines(True),
                                    fromfile='a/' + name, tofile='b/' + name))
patch_path = PROJECT / 'device/xiaomi/sheng/interfaces/kernel/6.18/camera-io-stride.patch'
patch_path.write_text(''.join(patch))
log = PROJECT / 'reports/device/kernel618-hardware-r36/current-kernel-root.txt'
assert '0xffee00000-0xffee96000' in log.read_text()
report = dict(revision='hardware-r37', date='2026-11-09', files=files,
              patch_sha256=sha(patch_path.read_bytes()),
              evidence=dict(file=str(log.relative_to(PROJECT)), sha256=sha(log.read_bytes()),
                            fault_iova='0xffee96000', mapping_iova='0xffee00000',
                            allocation_bytes=614400, output='IFE_FD (0x3004)', format='NV12',
                            width=852, y_height=480, uv_height=240, io_stride=852, uv_offset=409088,
                            raw_uv_end=613568, rounded_uv_last_write_end=616436,
                            error='SMMU fault exactly at end of FD mapping; capture requests subsequently stuck'),
              change='Only VFE780 uses raw IO plane stride when no explicit WM stride override exists',
              scope='Kalama VFE780 hardware table; other VFE versions and explicit overrides retain behavior',
              references=reference_records + [
                  dict(repository='selected-camera-integration', commit='c3956156ce7c4193c451dfda531fad72d35bfebb'),
                  dict(repository='LineageOS-piano', commit='3f10fc25273b42d18d0bd533551a0a5c3dda0094',
                       applicability='Different VFE generation; hardware table not copied'),
                  dict(repository='LineageOS-nuwa', commit='8e2b6ca4375919035587115189760eed64f14b8d',
                       applicability='Kalama device reference; vendor buffer layout remains unchanged')],
              userspace_abi_changed=False, root_components_added=False,
              build_result='pending', hardware_result='pending', camera_fixed=False,
              limitation='Explains the captured FD overrun; camera tilting, repeated recording and other fence faults require runtime verification')
receipt.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
