#!/usr/bin/env bash
# ACK, external modules and embedded module layer: all build stages use Bash.
set -euo pipefail
[ "${K618_LIMITS_VERIFIED:-}" = 1 ] || { echo 'Use bash build.sh'; exit 2; }
. "$(dirname -- "${BASH_SOURCE[0]}")/project-env.sh"
. "$PROJECT_ROOT/profiles/default.env"
config_only=0
stock_boot=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --config-only) config_only=1; shift;;
    --stock-boot) stock_boot=$(realpath -- "${2:?Missing boot.img path}"); shift 2;;
    *) echo 'Usage: bash build.sh [--config-only] [--stock-boot /path/to/boot.img]' >&2; exit 2;;
  esac
done
[ -f "$BUILD_ROOT/.sheng618-ready.json" ] || { echo 'Run bootstrap first'; exit 2; }
for command in make jq cpio depmod flex bison bc rsync sha256sum; do
  command -v "$command" >/dev/null || { echo "Missing host command: $command" >&2; exit 2; }
done
ack=$K618/ws/common
soc=$K618/soc
tp=$K618/vendor/qcom/opensource
output=$K618/out-gki
clang=$PREBUILTS/clang/host/linux-x86/clang-r584948c/bin
rust=$PREBUILTS/rust-toolchain/linux-x86/1.91.1.p3
tools=$PREBUILTS/kernel-build-tools/linux_musl-x86/bin
[ -x "$clang/clang" ] && [ -x "$rust/bin/rustc" ] && [ -f "$ELFUTILS/include/elfutils/libdw.h" ] || {
  echo 'Prepare pinned toolchains and elfutils; see docs/BUILD.zh-CN.md' >&2; exit 2;
}
export PATH="$clang:$rust/bin:$PREBUILTS/clang-tools/linux-x86/bin:$tools:$PREBUILTS/build-tools/linux-x86/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export LIBCLANG_PATH="${clang%/bin}/lib" RUSTC_BOOTSTRAP=1
export RUST_LIB_SRC="$rust/lib/rustlib/src/rust/library"
export KBUILD_GENDWARFKSYMS_STABLE=1 LOCALVERSION=
export MAKEFLAGS="HOSTCFLAGS=-O2\ -I$ELFUTILS/include HOSTLDFLAGS=-L$ELFUTILS/lib\ -Wl,-rpath,$ELFUTILS/lib"
mkdir -p "$output" "$PROJECT_ROOT/logs/$TAG" "$PROJECT_ROOT/dist/$TAG"
exec > >(tee "$PROJECT_ROOT/logs/$TAG/build.log") 2>&1
rm -f -- "$output/build-result.json"
make_cmd=(make -C "$ack" "O=$output" ARCH=arm64 LLVM=1 LLVM_IAS=1 "PAHOLE=$tools/pahole" "-j$JOBS")
run() {
  local label=$1
  shift
  echo "[$label]"
  if ! "$@" > "$output/$label.log" 2>&1; then tail -60 "$output/$label.log"; return 1; fi
}
cp "$PROJECT_ROOT/profiles/release.config" "$output/.config"
"$ack/scripts/config" --file "$output/.config" --set-str INITRAMFS_SOURCE '' --disable SHENG_BOOTLOG
run kernel-config "${make_cmd[@]}" olddefconfig
if grep -Eq '^CONFIG_(KSU|SUSFS|SHENG_BOOTLOG)[A-Z0-9_]*=(y|m)$' "$output/.config"; then
  echo 'Unexpected root or test logger configuration' >&2; exit 1
fi
if [ "$config_only" = 1 ]; then echo 'Fresh release configuration passed.'; exit 0; fi
run kernel "${make_cmd[@]}" Image modules
awk -F '\t' '$3 == "vmlinux"' "$output/Module.symvers" | sort > "$output/kernel-symbols.before"
run soc "${make_cmd[@]}" "M=$soc" modules
symbols=("$soc/Module.symvers")
legacy=$K618/vendor/xiaomi/adsprpc-515
rpc_flags=("SOC=$soc" CONFIG_ARCH_KALAMA=y
  "NOSTDINC_FLAGS=-nostdinc -I$soc/include -I$soc/include/uapi"
  "KCFLAGS=-include $K618/tp-autoconf.h")
plan=$PROJECT_ROOT/profiles/techpacks.json
multimedia=$(jq -r .multimedia_includes "$plan")
network=$(jq -r .network_includes "$plan")
expand() {
  local value=$1 stage=$2
  value=${value//'%M'/$multimedia}
  value=${value//'%R'/$network}
  value=${value//'%C'/CONFIG_ARCH_CANOE=y}
  value=${value//'%L'/-DCONFIG_RMNET_LA_PLATFORM=1}
  value=${value//'%I'/-DCONFIG_IPA3=1}
  value=${value//'%D'/$stage}
  value=${value//'%P'/${stage%/*}}
  value=${value//'%T'/$tp}
  value=${value//'%W'/$ack}
  value=${value//'${NFC_TRACE:+-DK618_NFC_TRACE}'/}
  printf '%s' "$value" | tr '\n' ' '
}
while IFS= read -r item; do
  name=$(jq -r '.[0]' <<< "$item")
  directory=$(jq -r '.[1]' <<< "$item")
  variables=$(jq -r '.[2]' <<< "$item")
  incs=$(jq -r '.[3]' <<< "$item")
  defs=$(jq -r '.[4]' <<< "$item")
  case "$name" in video|eva) continue;; esac
  stage=$(realpath -- "$tp/$directory")
  extra_symbols=("${symbols[@]}")
  if [ "$name" = eva515 ]; then
    run rpc-before-eva "${make_cmd[@]}" "M=$legacy" modules "${rpc_flags[@]}" "KBUILD_EXTRA_SYMBOLS=$soc/Module.symvers"
    incs="$legacy/include $incs"
    defs="$defs -DCONFIG_MSM_ADSPRPC=1"
    extra_symbols=()
    for path in "${symbols[@]}"; do
      [ "$path" = "$tp/dsp-kernel/Module.symvers" ] || extra_symbols+=("$path")
    done
    extra_symbols+=("$legacy/Module.symvers")
  fi
  read -r -a include_paths <<< "$(expand "$incs" "$stage")" || true
  nostdinc="-nostdinc -I$soc/include -I$soc/include/uapi"
  for path in "${include_paths[@]}"; do nostdinc+=" -I$path"; done
  read -r -a variables_array <<< "$(expand "$variables" "$stage")" || true
  run "tp-$name" "${make_cmd[@]}" "M=$stage" modules CONFIG_ARCH_KALAMA=y \
    "KERNEL_SRC=$ack" "KERNEL_ROOT=$ack" "KBUILD_EXTRA_SYMBOLS=${extra_symbols[*]}" \
    "NOSTDINC_FLAGS=$nostdinc" "KCFLAGS=-Wno-error -include $K618/tp-autoconf.h $(expand "$defs" "$stage")" \
    "${variables_array[@]}"
  symbols+=("$stage/Module.symvers")
done < <(jq -c '.modules[]' "$plan")
for group in pogo cs35l43 touch fingerprint hall keyboard ps5169; do
  stage=$K618/sheng-ports/$group
  run "tablet-$group" "${make_cmd[@]}" "M=$stage" modules "SOC=$soc" "KBUILD_EXTRA_SYMBOLS=${symbols[*]}"
  symbols+=("$stage/Module.symvers")
done
run loader "${make_cmd[@]}" "M=$K618/mark" modules
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
artifacts=$(jq -n --arg image "$(sha256sum "$output/Image" | cut -d' ' -f1)" '{Image: $image}')
boot_packaged=false
if [ -n "$stock_boot" ]; then
  [ "$(sha256sum "$stock_boot" | cut -d' ' -f1)" = 4156a2369f78bc5df61b6a521b07a508dedf20d5e63c207d30986ae37df3eaea ] || {
    echo 'Stock boot template does not match sheng OS3.0.303.0'; exit 1;
  }
  bash "$PROJECT_ROOT/tools/pack-boot.sh" "$output/Image" "$stock_boot" "$output"
  artifacts=$(jq --arg sha "$(sha256sum "$output/boot.img" | cut -d' ' -f1)" '. + {"boot.img": $sha}' <<< "$artifacts")
  boot_packaged=true
fi
jq -n --arg release "$release" --argjson artifacts "$artifacts" --argjson boot "$boot_packaged" \
  --arg snapshot "$(jq -r .sha256 "$PROJECT_ROOT/provenance/source-cache.json")" \
  '{release: $release, module_count: 344, exports_and_crcs_verified: true, boot_packaged: $boot, artifacts: $artifacts, source_snapshot_sha256: $snapshot}' \
  > "$output/build-result.json"
dist=$PROJECT_ROOT/dist/$TAG
cp "$output/Image" "$output/build-result.json" "$dist/"
if [ "$boot_packaged" = true ]; then cp "$output/boot.img" "$dist/"; fi
(cd "$dist"; sha256sum Image build-result.json > SHA256SUMS; if [ "$boot_packaged" = true ]; then sha256sum boot.img >> SHA256SUMS; fi)
echo "Built $dist/Image ($release, 344 modules)"
