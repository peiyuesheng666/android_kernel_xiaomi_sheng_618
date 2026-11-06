# sheng source policy

All board fixes live in `device/xiaomi/sheng`. Public repositories must match
the upstream revisions pinned by the ROM manifest before compilation. Device
modules use their own Soong identities. Services keep their Binder names while
using unique binary/RC filenames; PAL uses preferred-prebuilt selection with a
device-compiled ELF input. Package `overrides` alone cannot prevent same-path
Make installation collisions. No normal build patches a public repository.

The `seventeen` piano tree is an organizational reference, at revision
`3f10fc25273b42d18d0bd533551a0a5c3dda0094`. Its board values and firmware are
not sheng inputs. The sheng tree uses `aidl/sensors`, `configs/`, `display/`,
`audio/`, `compat/`, `dolby/`, `overlay/` and `docs/` for its own components.

Before building, run the following from an existing ROM checkout:

```sh
python3 device/xiaomi/sheng/scripts/audit_upstream_sources.py --fetch \
    --output /tmp/sheng-upstream-source-audit.json
bash device/xiaomi/sheng/scripts/build_hardware.sh
```

The audit fetches each previously edited public repository's exact pinned
revision again, verifies `FETCH_HEAD == HEAD`, checks both staged and unstaged
changes and untracked sources, and scans all repo-managed projects for changes.
It never changes a checkout or replaces the manifest's kernel/BSP versions with
unrelated branch tips. A network/fetch failure is a failure, not a clean result.

The local hardware-build helper uses the provisioned 80 GiB swap, 24 jobs
with two concurrent high-memory jobs,
compressed 10 GiB ccache and standard Ninja. On the 20 GiB WSL host it temporarily
wraps the generated Soong executable to set Go's 12 GiB memory limit and restores
that executable on exit. This is build-environment handling under `out/`, not
a platform source patch or an installed device component. Regular ROM builds
can use the ordinary LineageOS build commands on a sufficiently provisioned host.

`SOURCE_BASELINES.json` records the upstream inputs of device-owned source
snapshots. `patches/` holds historical diffs for review and provenance only;
they are not build steps. The extraction hook changes only the generated
`vendor/xiaomi/sheng/Android.bp` to export this tree's GSL headers and reference
its compatible Dolby filegroups.
Stock partition inputs remain read-only.

Each newly completed logical fix gets a separate commit and a record of its
build and hardware validation. A successful compile alone is not a hardware
test. Finish compiling, flashing and testing the current batch before working
on the remaining camera, display/color, input and Bluetooth issues.
