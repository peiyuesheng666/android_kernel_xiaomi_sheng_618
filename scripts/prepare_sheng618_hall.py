#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage native Linux input reporting for sheng's verified hall interrupts."""
import hashlib
import json
import shutil
from build_sheng618_upstream import ROOT, PROJECT, K618

stage = K618/'sheng-ports/hall'
stage.mkdir(parents=True, exist_ok=True)
source = PROJECT/'device/xiaomi/sheng/interfaces/kernel/6.18/sheng_hall.c'
shutil.copyfile(source, stage/'sheng_hall.c')
kbuild = '# SPDX-License-Identifier: GPL-2.0-only\nobj-m += xiaomi_hall.o\nxiaomi_hall-y := sheng_hall.o\n'
(stage/'Kbuild').write_text(kbuild)
files = {p.name: dict(staged_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
         for p in (stage/'sheng_hall.c', stage/'Kbuild')}
stock = ROOT/'diagnostic/disklog-r5/live.dts'
binary = ROOT.parent/'sheng-lineage/firmware-dump/hardware/modules/vendor_dlkm/xiaomi_hall.ko'
(PROJECT/'reports/kernel618-hall-source.json').write_text(json.dumps(dict(
    files=files,
    implementation='Native Linux input switches, Linux 6.18 gpio-keys/PM API conventions',
    kernel_reference='ACK ff4a6c3bb0f471a9dd186293a47b62c83829b97d',
    applicability='No matching sheng-hall implementation in selected integration or local LOS/MiCode sources',
    binding_reference=dict(path=str(stock), sha256=hashlib.sha256(stock.read_bytes()).hexdigest()),
    binary_reference=dict(path=str(binary), sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        observations='irq_handler 0x1700..0x1794: open=!active_low, close=active_low; probe requests named open/close SMP2P IRQs with RISING|ONESHOT'),
    preserved='Live DT GPIO171/172, EV_SW codes0/1, active-low polarity, two named SMP2P IRQs per child',
    limitations='Private character-device algorithm switching not implemented; physical cover operation still requires user acceptance',
    hardware_result='pending'), indent=2)+'\n')
print('Staged sheng native hall input switches')
