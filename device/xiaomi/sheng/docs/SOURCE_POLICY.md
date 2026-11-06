# sheng source policy

All board fixes live in `device/xiaomi/sheng`. Public repositories must match
the upstream revisions pinned by the ROM manifest before compilation. Device
modules may replace installed modules with their own Soong identities and
`overrides`; no normal build applies a patch to a public repository.

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

`SOURCE_BASELINES.json` records the upstream inputs of device-owned source
snapshots. `patches/` holds historical diffs for review and provenance only;
they are not build steps. The GSL extraction hook changes only the generated
`vendor/xiaomi/sheng/Android.bp` so it exports this tree's header provider.
Stock partition inputs remain read-only.

Each newly completed logical fix gets a separate commit and a record of its
build and hardware validation. A successful compile alone is not a hardware
test. Finish compiling, flashing and testing the current batch before working
on the remaining camera, display/color, input and Bluetooth issues.
