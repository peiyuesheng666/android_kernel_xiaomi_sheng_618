# Corrected display-core runtime trial, 2026-11-07

The failed r14 images and frozen spec remain preserved and rejected. The
corrected owning-container adapter compiled successfully and was tested by
`test_sheng_color_runtime.sh` on recovered r13, without partition writes.
Candidate SHA256: d3908ae8be949614ad63a0b884927bb390df6e9327771a5ae0905c212c0fa303.

The guard temporarily bound the candidate in init's mount namespace, restarted
composer, and observed one stable composer PID (6112) throughout the 90-second
trial. The stock color library accepted the object and no composer crash
occurred. Original r13 had PCC/gamut property values 0. The corrected candidate
produced nonzero hardware DSPP PCC/gamut blobs on CRTC 176.

RGB blue=0.6 produced the hardware PCC diagonal 0x8000, 0x8000, 0x4ccd
(1.0, 1.0, approximately 0.6 in Q15). The user explicitly confirmed that white
became visibly yellow. The corresponding SurfaceFlinger dump shows all six
visible layers as DEVICE and the SDM stack as Device/Device. No GPU fallback
or SELinux relaxation was used. This accepts this temporary RGB hardware path;
it does not yet establish persistent-boot or all-feature acceptance.

With neutral RGB and Night Light at 2850 K, the PCC diagonal became
0x8000, 0x5fd9, 0x4135, matching the requested warm transform. color_display
reported activated=true and 2850 K. Physical Night Light feedback was requested
but remains pending; a register response alone is not physical acceptance.
Ambient DWB overlays were absent from the running r13 trial, so ambient
adaptation and the revised mode menu were not tested here.

After 90 seconds the guard detached its busy bind mount, verified the original
library hash 5f7226abc1ef594fb7e15e89bbf54ee835d49001cefad777182ae8b7a229cb03,
and restarted composer (9111). The restart briefly makes framework services
unavailable. Settings restoration was retried once services returned: Night
Light activated=0, temperature key absent, original RGB float bits
[0x3f800000,0x3f800000,0x3f1a43ff]. The unchanged auto-mode key was absent.
The first restoration attempt made no settings writes while services were
unavailable. No camera, screenshot, AON, erase or slot change was used.

Raw evidence is under workspace reports/device/r14-boot-failure:
- r13-pcc-baseline.txt
- owned-trial-before-rgb.txt / owned-trial-blue60.txt
- owned-trial-night2850.txt
- owned-trial-restored.txt / owned-trial-final-settings.txt

The later explicit 300-second observation also completed and restored the
same r13 hash. The retained night-trial-off.txt records composer PID 11771
and neutral PCC diagonal 0x8000/0x8000/0x8000 with Night Light off. Current
readback confirms boot_completed=1, composer running and no candidate library
installed. Night Light's temperature key is now 2850; activation is false.
The extended guard still defaults to 90 seconds, accepts only 30-300 seconds
and keeps the same PID, hash and mount-identity checks. Physical Night Light
acceptance remains pending.

Next persistent batch is r15 against the exact recovered r13 baseline. The
packer and flash entry now target only r15 and require a new exclusive frozen
spec; old r14 artifacts must never be overwritten. Scope remains two ODM
overlays, vendor lib64/libsdmcore.so, and their vbmeta parent.
