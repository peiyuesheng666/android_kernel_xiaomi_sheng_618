# Touch firmware: no fixed boot wait (r26 candidate)

The user's r25 report was a short interval with no touch after the UI appeared.
The captured boot shows firmware loading at 17.400s, after boot animation exit
at about 15.3s. The OEM queue delay is 3500 jiffies, or 14 seconds at CONFIG_HZ=250.
Firmware transfer itself took about 103ms in that boot.

The device-owned modules_install transform now disables the early queue call
and queues the same firmware work with zero delay at the successful probe tail.
Simply changing the early delay to zero was rejected: update_pen_status takes
ts+0x240, whose mutex is initialized at .text+0x76f4, after the old queue call at
0x7028. Both successful probe paths reach the new queue at 0x7fbc, after that
mutex, the pen state, resume work and common-data registration are initialized.
Fatal cleanup paths bypass the new queue. The final timestamp printk block is
reused; firmware, callbacks, locks, error exits, ELF sizes/sections, vermagic and
import/export CRCs remain unchanged. Relocations are explicitly moved; unused
slots use R_AARCH64_NONE, supported by the pinned arm64 module loader.

Validation completed:

- Exact OEM SHA and instruction/symbol/relocation guards passed.
- llvm-objdump confirms the new call arguments and relocations, delay=0.
- The actual board Makefile modules_install flow staged 417 BSP modules and
  checked all 419 effective modules, including source zram/zsmalloc: no ABI errors.
- Unknown input, repeat patch, nonzero delay and wrong HZ are rejected.
- OEM input remains SHA256 a1f3f907f4519eaf3d63243561fc32c7f75337188a3953b3857bcad60135233f.
- Candidate SHA256 edf8001b0965f0e6d5005a7d8605a1b77d1d2949049c7ee5ef13a23a045db9e1.
- Postbuild physical audit passed: all 1,243 projects clean and all 20 audited
  public source repositories match pinned upstream content.

Evidence: /root/sheng-lineage/hardware-diagnostics/r26-touch-zero/ and the
fresh-fetch prebuild audit r26-prebuild-audit-20261108.json in its parent.
The firmware still needs real transfer time; zero artificial delay does not
mean a physically instantaneous controller start. This is not a complete ROM
build or a runtime pass. Packaging, AVB review and device validation are pending.
Only ca10ede3 / slot b may be used; recovery and the other tablet are excluded.
The camera's requested 90-degree counterclockwise correction remains pending.
