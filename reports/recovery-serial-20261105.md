# USB serial diagnostics for sheng, 2026-11-05

- User reports r2 starts but still restarts to fastboot before Recovery UI. Treat r2 as failed hardware startup. The exact stage remains unproven until logs; do not turn that description into a claim that kernel or init completed.
- User cannot use the suggested pstore path and explicitly requested building our own serial diagnostics. Stock kernel config has PSTORE/RAMOOPS enabled, but configured support does not prove that the runtime buffer exists or is accessible. Do not argue a generic kernel-version assertion instead of fixing this device.
- Original stock kernel also has USB_F_ACM, USB_U_SERIAL, USB_CONFIGFS_ACM/SERIAL built in. We use this existing support; no source-kernel replacement, UART pin guess or physical soldering is claimed.

## Implementation and actual checks

- Own source: device/xiaomi/sheng/recovery/serial_init.c. Statically linked AArch64 executable, compiled by the installed GNU cross compiler with -O2 -static -Wall -Wextra -Werror. No dynamic ELF interpreter. It checks PID1 before any mounts or module insertion. --self-test and --transport-test are deliberately side-effect-free host diagnostics.
- PID1 mounts only volatile diagnostic pseudo filesystems, emits stage/module messages to /dev/kmsg, and forks an early logger with an8MiB backlog. Original raw stock modules are inserted with finit_module flags0; errors are logged, not converted into success. No module CRC/vermagic bypass. USB prerequisites are prioritized after first-stage resources.
- Original stock modules.blocklist is restored, including llcc_perfmon. r2's depmod reconstruction had lost this file. Another concrete omission: r2 lacked mtdoops.mtddev; matching kernel drivers/mtd/mtdoops.c returns EINVAL when that parameter is empty. r3 adds mtdoops.mtddev=0 and forwards it through both pre-init loader options and Android's cmdline parser. Without a crash log this is a documented blocker/candidate, not proof of the user's complete failure chain.
- Own ACM gadget uses VID1D6B/PID0104, serialSHENG-DIAG-R3. The native logger reads raw kmsg, buffers logs before host connection, and accepts only GO. No remote shell. Raw logger continues across exec into the original Lineage /system/bin/init; post-handoff SELinux/service lifecycle may affect it and is not yet hardware proven.
- Modem firmware is mounted read-only, its sysfs block numbers are discovered rather than assuming a partition number, and ADSP is started once only if firmware is present. Diagnostic userspace contains no flash/format commands; this does not promise that every stock driver has no internal normal-runtime persistence.
- Real AArch64 executable ran under qemu-aarch64. Actual logger transmitted494667 bytes through a Linux PTY; all bytes matched SHA256b69549ba83d173bcfaa421eb965bb2fb4db5f364530301993ca06e3fcb9a0ddc. Unrelated input did not continue init; GO created the expected marker and returned successfully. Report: reports/serial-transport-test.json. This is transport validation, not USB hardware validation.
- Own scripts/build_serial_recovery.py repackages r2's verified userspace/stock kernel container with static diagnostic /init and dependency-ordered module bootstrap. The original /system/bin/init stays intact. Final embedded kernel/DTB/DTBO hashes equal r2, AVB verify_image passes, and Windows independent SHA256 agrees.

## Current artifact and capture process

- artifacts/recovery-sheng-lineage-24.0-r3-serial/lineage-24.0-sheng-recovery-r3-serial.img,100MiB, SHA2564367acd06b61b6d3699134865b622220411a81e9167ee40c95e867d3ce57f90a. Diagnostic only, not a working-ROM claim.
- Windows collector scripts/capture_recovery_serial.ps1 actually started22:47:43, PID16088, tool session41137. reports/serial/capture-state.json sayswaiting-for-sheng-usb-serial, bytes0. Exact raw log path is in that state. It polls the Windows serial device inventory cheaply and reads continuously on connection, without model/token polling.
- Collector opens only the selected diagnostic VID/PID (or an explicit port), DTR=true, raw byte logging. It sends GO only once the HOLD-before-Android record has already been received and at least5 seconds have passed. Thus earlier logs are saved before handoff; no blind timer advances a stalled module load. It reconnects after USB disconnect and exits after120 minutes.
- No physical fastboot boot, flash, reboot or format has been issued by us. Next required external action is the user's temporary fastboot boot of r3. Then inspect the raw log/state rather than regenerating another unobserved recovery. If USB never comes up, physical UART requires genuine board access and pinout; that cannot be manufactured by software.

## Main ROM status

- The tree remains a compiling bring-up draft, not an adapted/bootable ROM. Original full ZIP, source5.15.220 startup and r2 all lack successful hardware startup. User's criticism was acknowledged directly.
- device-audit.pending blocks blindly restarting the full ROM from the old validation receipt. No automatic full build or quota automation is active.
- Current meaningful goal is startup logs and Recovery UI first; source-kernel and full ROM verification follow actual evidence. Do not again equate CRC/build success with hardware boot.
