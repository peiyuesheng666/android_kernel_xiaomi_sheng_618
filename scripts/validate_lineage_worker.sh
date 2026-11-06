#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=/root/sheng-lineage
rom="$root/lineage-24.0"
printf 'validating\n' > "$root/logs/build-phase.txt"
printf 'validating\n' > "$root/logs/build-status.txt"
bash "$here/setup_rom_workspace.sh"
source "$here/rom_build_settings.sh"
static_result=0
for checker in preflight_sheng.py verify_dolby.py audit_install_collisions.py; do
    case "$checker" in
        preflight_sheng.py) flags=(--require-synced);;
        audit_install_collisions.py) flags=(--require-clean);;
        *) flags=();;
    esac
    python3 "$here/$checker" "${flags[@]}" || static_result=1
done
if [[ "$static_result" != 0 ]]; then
    printf 'validation-static-failed\n' > "$root/logs/build-status.txt"
    exit 1
fi
cd "$rom"
set +u
source build/envsetup.sh
lunch lineage_sheng-cp2a-userdebug
set -u
# -k0 is the supported keep-going flag: collect independent failures in one run.
# No bacon/droid/OTA target is requested here.
targets=(selinux_policy check-vintf-all check-elf-files MODULES-IN-vendor-xiaomi-sheng kernel ShengDolby
    FrameworkResOverlaySheng SystemUIResOverlaySheng SettingsResOverlaySheng
    LineageResOverlaySheng WifiResOverlaySheng
    android.hardware.audio.service android.hardware.audio@7.1-impl
    android.hardware.audio.effect@7.0-impl audio.primary.kalama
    android.hardware.soundtrigger@2.3-impl
    android.hardware.graphics.mapper@4.0-impl-qti-display
    vendor.qti.hardware.display.demura-service
    vendor.qti.hardware.display.allocator-service
    vendor.qti.hardware.display.composer-service
    android.hardware.biometrics.fingerprint-service.xiaomi
    android.hardware.health-service.qti android.hardware.health-service.qti_recovery
    android.hardware.sensors-service.xiaomi-multihal
    android.hardware.power-service-qti android.hardware.thermal-service.qti
    android.hardware.usb-service.qti android.hardware.usb.gadget-service.qti
    android.hardware.wifi-service vendor.lineage.touch-service.xiaomi
    vendor.lineage.health-service.default android.hardware.boot-service.qti
    android.hardware.boot-service.qti.recovery vendor.qti.qspa-service
    vendor.qti.hardware.vibrator.service fastbootd)
printf '%s\n' "${targets[@]}" > "$root/logs/validation-targets.txt"
set +e
m -j"$SHENG_BUILD_JOBS" -k0 "${targets[@]}" > "$root/logs/build-lineage.log" 2>&1
result=$?
set -e
python3 "$here/audit_policy_types.py"
python3 "$here/summarize_validation.py" --returncode "$result"
if [[ "$result" == 0 ]]; then
    printf 'validated\n' > "$root/logs/build-status.txt"
    printf 'prebuild-validation-passed\n' > "$root/logs/build-phase.txt"
else
    printf 'validation-failed:%s\n' "$result" > "$root/logs/build-status.txt"
fi
exit "$result"
