# Thermal daemon file ownership

r31 boot logs contain three SELinux capability `chown` denials for mi_thermald.
The daemon runs with uid 0 and gid 1000, but its SELinux domain lacks the original
firmware's chown and fowner permissions. Its four thermal state files remain
root:system instead of the system:system ownership requested by the executable.

The unchanged original binary has four chown calls, each with uid/gid 1000:

| Call address | File |
| --- | --- |
| 0x9b5f0 | /data/vendor/thermal/report.dump |
| 0x9b64c | /data/vendor/thermal/thermal.dump |
| 0x9b6a8 | /data/vendor/thermal/last_thermal.dump |
| 0x9b73c | /data/vendor/thermal/thermal-global-mode |

Each is preceded by chmod: 0664 for report.dump and thermal-global-mode, 0644
for the other two. Once the first successful run transfers ownership to system,
the root daemon needs fowner to perform those chmod operations on later boots.
The original vendor CIL grants exactly these two capabilities together.

Restore those two permissions only to mi_thermald. Existing thermal_data_file
setattr permissions still constrain the affected files; this change adds no
file allow rule, relabeling, permissive domain, broad app permission or binary
patch. Do not add the other stock capabilities without separate evidence.

Source correction and isolated policy compilation passed, including neverallow
checks and byte-identical reproduction of the r31 baseline. A comparison of
3671 existing types found only the two requested thermal capability permissions
plus the independent face frontend's HIDL-manager lookup; no existing permission
was removed. No new permissive domain was introduced. Candidate installation and
Enforcing runtime acceptance, including a second boot after ownership transfer,
remain pending.

## r32 runtime and creation-only fourth path

r32 was installed and its seven partition hashes and fourteen payload hashes
passed guarded readback after temporary recovery from the independent charging
HAL startup stall. Under Enforcing, the daemon itself changed report.dump,
thermal.dump and last_thermal.dump to system:system, with the expected modes.
No thermal ownership was changed manually. A subsequent boot is still needed
to check fowner on those now system-owned files.

thermal-global-mode remains root:system 0664 with its old 1970 timestamp. Further
review of the same original disassembly corrects the initial expectation that
all four paths would be chowned on every boot: access(F_OK) at 0x9b6e0 branches
directly to 0x9b7a8 if this fourth file exists. Its open/chmod/chown sequence,
including chown at 0x9b73c, runs only when the file is absent. The first three
paths have unconditional chmod/chown calls. Therefore the unchanged fourth
file does not establish a continuing capability denial. Its new-file creation
branch has not been tested; the existing user state was preserved.

See r32-boot-charging-control-20261108.md for the exact recovery scope. Do not
claim four-file migration, creation-branch acceptance, or a second-boot pass
from the first r32 boot.
