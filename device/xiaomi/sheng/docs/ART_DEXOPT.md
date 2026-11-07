# ARM64 ART compiler selection

The device product previously inherited `core_64_bit.mk`, which selects
`ro.zygote=zygote64_32`. BoardConfig defines only ARM64, the installed ABI list
contains only `arm64-v8a`, and the ART APEX contains `dex2oat64` without
`dex2oat32`. The missing `dalvik.vm.dex2oat64.enabled` property made artd select
the absent 32-bit compiler even for ARM64 applications.

On 2026-11-07, background dexopt repeatedly aborted with `Failed to execute
/apex/com.android.art/bin/dex2oat32: No such file or directory`. The affected
jobs included AppSearch, TrustedUIService and IWlanService. This establishes a
compiler configuration failure; it does not establish that every application
crash has the same cause.

`lineage_sheng.mk` now inherits the unmodified upstream
`build/make/target/product/core_64_bit_only.mk` before `full_base.mk`. This
standard product sets `ro.zygote=zygote64`, enables the existing 64-bit compiler
and explicitly declares the already ARM64-only application ABI. The piano
seventeen Lineage and custom product entries use the same upstream product.
No platform or ART sources are patched, and no compiler binary is copied.

Upstream selection is in `art/artd/artd.cc`, `Artd::ShouldUseDex2Oat64()`:
it requires a nonempty 64-bit ABI list and the enabled property, whose default
is false. `Artd::GetDex2Oat()` then selects the 32- or 64-bit binary.

For a bounded runtime test, the nonpersistent property
`dalvik.vm.dex2oat64.enabled=true` was set on the running r11 system. These two
commands both returned `Success`:

```sh
cmd package compile -m verify -f org.lineageos.sheng.dolby
cmd package compile -m verify -f com.android.settings
```

artd logged the actual `dex2oat64` command and exit code zero. The commands
compile application bytecode without opening either application. The temporary
property remains active for this boot to prevent the observed failure; the
compiled product must supply it after reboot. No zygote, display service or
device restart was performed for the test.

## r13 reboot acceptance, 2026-11-07

The permanent vendor properties and runtime readback are both
`ro.zygote=zygote64` and `dalvik.vm.dex2oat64.enabled=true`; the ABI is
`arm64-v8a`. No temporary property was set for this acceptance. Both commands
above were run once with a 30-second bound and returned `Success`, exit zero.
artd PID 6301 logged `/apex/com.android.art/bin/dex2oat64` with the corresponding
APK paths and returned code zero for each: Settings at 06:44:45.719 UTC and
ShengDolby at 06:44:46.006 UTC.

Evidence is indexed by `runtime-r13-20261107.json` and retained in the workspace
`reports/device/r13-runtime/art-*`. This verifies these two compilation paths;
full application startup and other application crashes remain independent tests.
