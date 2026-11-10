#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "${BASH_SOURCE[0]}")/scripts/build-env.sh"
if [ "${1:-}" = --help ]; then echo 'Usage: bash embed.sh'; exit 0; fi
[ "$#" = 0 ] || { echo 'Usage: bash embed.sh'; exit 2; }
start_stage embed "$@"
require_toolchain
require_commands cpio depmod
require_kernel
[ -f "$output/.modules-ready.json" ] || { echo 'Run bash buildmodules.sh first.'; exit 2; }
mapping=$PROJECT_ROOT/profiles/module-sources.json
for pair in "kernel-symbols.before:kernel_symbols_sha256" "module-build-hashes.tsv:module_hashes_sha256"; do
  file=${pair%%:*}; key=${pair#*:}
  [ "$(sha256sum "$output/$file" | cut -d' ' -f1)" = "$(jq -r ".$key" "$output/.modules-ready.json")" ] || { echo "Changed module state: $file"; exit 2; }
done
[ "$(sha256sum "$mapping" | cut -d' ' -f1)" = "$(jq -r .module_map_sha256 "$output/.modules-ready.json")" ] || { echo 'Module map changed; rerun buildmodules.sh.'; exit 2; }
while IFS=$'\t' read -r name source; do
  case "$source" in out/*) path=$output/${source#out/};; *) path=$K618/$source;; esac
  want=$(awk -F '\t' -v name="$name" '$1 == name {print $2}' "$output/module-build-hashes.tsv")
  [ "$(sha256sum "$path" | cut -d' ' -f1)" = "$want" ] || { echo "Changed module: $name; rerun buildmodules.sh."; exit 2; }
done < <(jq -r 'to_entries[] | [.key, .value] | @tsv' "$mapping")
invalidate_result
rm -f -- "$output/.embed-ready.json"
layer=$output/layer
mkdir -p "$layer"
cp -a "$PROJECT_ROOT/profiles/module-layer/." "$layer/"
modules=$layer/lib/modules
mapping=$PROJECT_ROOT/profiles/module-sources.json
[ "$(jq length "$mapping")" = 344 ] || { echo 'Module map must contain 344 modules'; exit 1; }
while IFS=$'\t' read -r name source; do
  case "$source" in out/*) path=$output/${source#out/};; *) path=$K618/$source;; esac
  [ -f "$path" ] || { echo "Missing built module: $path"; exit 1; }
  cp "$path" "$modules/$name"
  "$clang/llvm-strip" --strip-debug "$modules/$name"
done < <(jq -r 'to_entries[] | [.key, .value] | @tsv' "$mapping")
[ "$(find "$modules" -maxdepth 1 -name '*.ko' | wc -l)" = 344 ] || { echo 'Unexpected module count'; exit 1; }
run usermode-loader "$clang/clang" --target=aarch64-linux-gnu -O2 -nostdlib -static \
  -ffreestanding -fno-stack-protector -fuse-ld=lld -Wl,--build-id=none -s \
  -o "$layer/k618_umh" "$PROJECT_ROOT/tools/k618_umh.c"
release=$(cat "$output/include/config/kernel.release")
dep_root=$output/depmod-root
target=$dep_root/lib/modules/$release
mkdir -p "$target/kernel"
cp "$modules/"*.ko "$target/kernel/"
cp "$output/modules.builtin" "$output/modules.builtin.modinfo" "$target/"
jq -r 'keys[] | "kernel/" + .' "$mapping" > "$target/modules.order"
if ! depmod -b "$dep_root" -F "$output/System.map" -e "$release" 2> "$output/depmod-errors.log"; then
  cat "$output/depmod-errors.log"; exit 1
fi
[ ! -s "$output/depmod-errors.log" ] || { cat "$output/depmod-errors.log"; exit 1; }
run module-abi "$PYTHON" "$PROJECT_ROOT/tools/verify-module-abi.py" "$output" "$modules"
for name in modules.dep modules.alias modules.softdep; do
  sed 's|kernel/|/lib/modules/|g' "$target/$name" > "$modules/$name"
done
(cd "$layer"; find . -mindepth 1 -printf '%P\0' | sort -z | cpio --null -o -H newc -R 0:0 --quiet) > "$output/overlay.cpio"
"$ack/scripts/config" --file "$output/.config" --set-str INITRAMFS_SOURCE "$output/overlay.cpio" --disable INITRAMFS_FORCE
run embedded-config "${make_cmd[@]}" olddefconfig
run embedded-image "${make_cmd[@]}" Image
sort "$output/vmlinux.symvers" > "$output/kernel-symbols.after"
cmp "$output/kernel-symbols.before" "$output/kernel-symbols.after"
cp "$output/arch/arm64/boot/Image" "$output/Image"
image_sha=$(sha256sum "$output/Image" | cut -d' ' -f1)
jq -n --arg release "$release" --arg image "$image_sha" \
  --arg snapshot "$(jq -r .sha256 "$PROJECT_ROOT/provenance/source-cache.json")" \
  '{release: $release, module_count: 344, exports_and_crcs_verified: true, boot_packaged: false, artifacts: {Image: $image}, source_snapshot_sha256: $snapshot}' \
  > "$output/build-result.json"
jq -n --arg image "$image_sha" '{image_sha256: $image}' > "$output/.embed-ready.json"
publish_result
echo "Modules embedded: $dist/Image"
