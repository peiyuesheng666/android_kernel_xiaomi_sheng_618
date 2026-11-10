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
mkdir -p "$output"
invalidate_result
rm -f -- "$output/.kernel-ready.json" "$output/.modules-ready.json" "$output/.embed-ready.json"
cp "$PROJECT_ROOT/sheng_defconfig" "$output/.config"
"$ack/scripts/config" --file "$output/.config" --set-str INITRAMFS_SOURCE '' --disable SHENG_BOOTLOG
run kernel-config "${make_cmd[@]}" olddefconfig
if grep -Eq '^CONFIG_(KSU|SUSFS|SHENG_BOOTLOG)[A-Z0-9_]*=(y|m)$' "$output/.config"; then
  echo 'Unexpected root or test logger configuration' >&2; exit 1
fi
if [ "$config_only" = 1 ]; then echo 'sheng_defconfig configuration passed.'; exit 0; fi
run kernel "${make_cmd[@]}" Image
cp "$output/.config" "$output/kernel.config"
cp "$output/arch/arm64/boot/Image" "$output/kernel-Image"
jq -n --arg defconfig "$(sha256sum "$PROJECT_ROOT/sheng_defconfig" | cut -d' ' -f1)" \
  --arg config "$(sha256sum "$output/kernel.config" | cut -d' ' -f1)" \
  --arg image "$(sha256sum "$output/kernel-Image" | cut -d' ' -f1)" \
  '{defconfig_sha256: $defconfig, kernel_config_sha256: $config, kernel_image_sha256: $image}' > "$output/.kernel-ready.json"
echo "Kernel built: $output/kernel-Image"
