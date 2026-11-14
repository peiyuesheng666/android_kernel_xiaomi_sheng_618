#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "${BASH_SOURCE[0]}")/scripts/build-env.sh"
if [ "${1:-}" = --help ]; then echo 'Usage: bash buildkernel.sh [--config-only]'; exit 0; fi
config_only=0
if [ "${1:-}" = --config-only ] && [ "$#" = 1 ]; then config_only=1
elif [ "$#" != 0 ]; then echo 'Usage: bash buildkernel.sh [--config-only]'; exit 2; fi
start_stage buildkernel "$@"
require_toolchain
require_commands flex bison bc
if [ ! -f "$BUILD_ROOT/.sheng618-ready.json" ]; then bash "$PROJECT_ROOT/scripts/prepare.sh"; fi
"$PYTHON" "$PROJECT_ROOT/scripts/apply-droidspaces-fix.py"
"$PYTHON" "$PROJECT_ROOT/scripts/apply-scene-socinfo-fix.py"
"$PYTHON" "$PROJECT_ROOT/scripts/apply-pen-release-fix.py"
"$PYTHON" "$PROJECT_ROOT/scripts/apply-repair-r85.py"
"$PYTHON" "$PROJECT_ROOT/scripts/apply-pen-stability.py"
"$PYTHON" "$PROJECT_ROOT/scripts/apply-factory-interfaces.py"
"$PYTHON" "$PROJECT_ROOT/scripts/apply-walt-compatibility.py"
mkdir -p "$output"
invalidate_result
rm -f -- "$output/.kernel-ready.json" "$output/.modules-ready.json" "$output/.embed-ready.json"
cp "$PROJECT_ROOT/sheng_defconfig" "$output/.config"
"$ack/scripts/config" --file "$output/.config" --set-str INITRAMFS_SOURCE ''
if [ "$SHENG_BUILD_MODE" = debug ]; then
  "$ack/scripts/config" --file "$output/.config" --enable SHENG_BOOTLOG --set-val LOG_BUF_SHIFT 22
else
  "$ack/scripts/config" --file "$output/.config" --disable SHENG_BOOTLOG
fi
run kernel-config "${make_cmd[@]}" olddefconfig
for option in SYSVIPC POSIX_MQUEUE IPC_NS PID_NS DEVTMPFS USER_NS NETFILTER_XT_MATCH_ADDRTYPE; do
  grep -qx "CONFIG_${option}=y" "$output/.config" || { echo "Missing Droidspaces option: $option"; exit 1; }
done
for option in IPVLAN MACVLAN VXLAN BRIDGE BRIDGE_VLAN_FILTERING VLAN_8021Q OVERLAY_FS; do
  grep -qx "CONFIG_${option}=y" "$output/.config" || { echo "Missing container network/filesystem option: $option"; exit 1; }
done
grep -qx '# CONFIG_ANDROID_BINDER_IPC_RUST is not set' "$output/.config" || {
  echo 'Unused Rust Binder must stay disabled with IPC namespaces'; exit 1;
}
if grep -Eq '^CONFIG_(KSU|SUSFS)[A-Z0-9_]*=(y|m)$' "$output/.config"; then
  echo 'Unexpected integrated root configuration' >&2; exit 1
fi
if [ "$SHENG_BUILD_MODE" = debug ]; then
  grep -qx 'CONFIG_SHENG_BOOTLOG=y' "$output/.config" || { echo 'Missing debug rawdump logger'; exit 1; }
else
  grep -qx '# CONFIG_SHENG_BOOTLOG is not set' "$output/.config" || { echo 'Release logger must be disabled'; exit 1; }
fi
for option in IP6_NF_NAT IP6_NF_TARGET_MASQUERADE NETFILTER_XT_NAT NETFILTER_XT_TARGET_MASQUERADE IP6_NF_IPTABLES_LEGACY NF_NAT; do
  grep -qx "CONFIG_${option}=y" "$output/.config" || { echo "Missing IPv6 NAT option: $option"; exit 1; }
done
if [ "$config_only" = 1 ]; then echo 'sheng_defconfig configuration passed.'; exit 0; fi
run kernel "${make_cmd[@]}" Image
cp "$output/.config" "$output/kernel.config"
cp "$output/arch/arm64/boot/Image" "$output/kernel-Image"
jq -n --arg defconfig "$(sha256sum "$PROJECT_ROOT/sheng_defconfig" | cut -d' ' -f1)" \
  --arg config "$(sha256sum "$output/kernel.config" | cut -d' ' -f1)" \
  --arg image "$(sha256sum "$output/kernel-Image" | cut -d' ' -f1)" \
  --arg walt "$(sha256sum "$PROJECT_ROOT/provenance/walt-compatibility.json" | cut -d' ' -f1)" \
  '{defconfig_sha256: $defconfig, kernel_config_sha256: $config, kernel_image_sha256: $image, walt_source_receipt_sha256: $walt}' > "$output/.kernel-ready.json"
echo "Kernel built: $output/kernel-Image"
