#!/usr/bin/env bash
# Build the device-owned hardware modules with unmodified platform sources.
set -euo pipefail
rom=${SHENG_ROM_ROOT:-/root/sheng-lineage/lineage-24.0}
cd "$rom"
# Re-enable the already provisioned build swap after a WSL restart.
for swap in /root/sheng-612/lineage-build.swap /root/sheng-lineage/lineage-extra.swap; do
    if [[ -f "$swap" ]] && ! swapon --show=NAME --noheadings | grep -Fxq "$swap"; then
        swapon --priority 0 "$swap"
    fi
done
python3 device/xiaomi/sheng/scripts/audit_upstream_sources.py --fetch \
    --output /root/sheng-lineage/logs/prebuild-upstream-source-audit.json
source build/envsetup.sh
lunch lineage_sheng-cp2a-userdebug
export USE_CCACHE=1 CCACHE_EXEC=/usr/bin/ccache
export CCACHE_DIR=/root/sheng-lineage/ccache CCACHE_COMPRESS=true
export SOONG_ALLOW_MISSING_DEPENDENCIES=false
export SOONG_NINJA=ninja
# The 20 GiB host cannot run many 4 GiB Java tools at once without swap thrashing.
export NINJA_HIGHMEM_NUM_JOBS=2
"$CCACHE_EXEC" --max-size=10G >/dev/null
# Finish the generated compiler's bootstrap before wrapping it. The temporary
# wrapper must not be replaced by a pending Ninja copy/link action.
if [[ -f out/soong/bootstrap.ninja ]]; then
    prebuilts/build-tools/linux-x86/bin/ninja -f out/soong/bootstrap.ninja \
        out/host/linux-x86/bin/soong_build
fi
# Soong's hermetic launcher strips environment variables. On this 20 GiB WSL
# host, use a temporary wrapper around the generated compiler output to pass
# Go's supported memory limit. Restore the output when this build finishes;
# public source and normal product builds are unaffected.
builder="$rom/out/host/linux-x86/bin/soong_build"
real_builder="$builder.sheng-real"
if [[ -f "$real_builder" ]]; then
    mv -f -- "$real_builder" "$builder"
fi
if [[ -f "$builder" ]]; then
    mv -- "$builder" "$real_builder"
    printf '#!/bin/sh\nexport GOMEMLIMIT=12GiB GOGC=40 GOMAXPROCS=4\nexec "%s" "$@"\n' "$real_builder" > "$builder"
    chmod 755 "$builder"
    # Do not invalidate an unchanged build graph just for the memory wrapper.
    touch -r "$real_builder" "$builder"
    restore_builder() {
        if head -c 2 "$builder" | grep -q '#!'; then
            mv -f -- "$real_builder" "$builder"
        else
            rm -f -- "$real_builder"
        fi
    }
    trap restore_builder EXIT
fi
targets=(
    audio.primary.sheng libar-pal
    android.hardware.sensors-service.sheng-multihal
    vendor.qti.hardware.display.composer-service-sheng
    vendor.qti.hardware.display.allocator-service-sheng libsdmdal libsdedrm
    libshgdolby_foundation libdlbdsservice libhwdap libdlbpreg libdlbvol
    out/target/product/sheng/vendor/build.prop out/target/product/sheng/odm/etc/build.prop
    ShengDolby FrameworkResOverlaySheng vendor_file_contexts selinux_policy file_contexts.bin
)
if [[ $# -gt 0 ]]; then
    targets=("$@")
fi
m -j"${SHENG_BUILD_JOBS:-$(nproc)}" "${targets[@]}"
