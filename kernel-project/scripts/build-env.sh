#!/usr/bin/env bash
# Shared environment and state checks for the four independent build stages.
. "$(dirname -- "${BASH_SOURCE[0]}")/project-env.sh"
. "$PROJECT_ROOT/profiles/default.env"
ack=$K618/ws/common
soc=$K618/soc
tp=$K618/vendor/qcom/opensource
output=$K618/out-gki
dist=$PROJECT_ROOT/dist/$TAG
clang=$PREBUILTS/clang/host/linux-x86/clang-r584948c/bin
rust=$PREBUILTS/rust-toolchain/linux-x86/1.91.1.p3
tools=$PREBUILTS/kernel-build-tools/linux_musl-x86/bin
export PATH="$clang:$rust/bin:$PREBUILTS/clang-tools/linux-x86/bin:$tools:$PREBUILTS/build-tools/linux-x86/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export LIBCLANG_PATH="${clang%/bin}/lib" RUSTC_BOOTSTRAP=1
export RUST_LIB_SRC="$rust/lib/rustlib/src/rust/library"
export KBUILD_GENDWARFKSYMS_STABLE=1 LOCALVERSION=
export MAKEFLAGS="HOSTCFLAGS=-O2\ -I$ELFUTILS/include HOSTLDFLAGS=-L$ELFUTILS/lib\ -Wl,-rpath,$ELFUTILS/lib"
make_cmd=(make -C "$ack" "O=$output" ARCH=arm64 LLVM=1 LLVM_IAS=1 "PAHOLE=$tools/pahole" "-j$JOBS")
start_stage() {
  local stage=$1
  shift
  if [ "${K618_LIMITS_VERIFIED:-}" != 1 ]; then
    exec "$PYTHON" "$PROJECT_ROOT/scripts/limit-run.py" bash "$PROJECT_ROOT/$stage.sh" "$@"
  fi
  mkdir -p "$PROJECT_ROOT/logs/$TAG" "$dist"
  exec > >(tee "$PROJECT_ROOT/logs/$TAG/$stage.log") 2>&1
}
require_commands() {
  local command
  for command in "$@"; do command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 2; }; done
}
require_toolchain() {
  require_commands make jq sha256sum
  [ -x "$clang/clang" ] && [ -x "$rust/bin/rustc" ] && [ -f "$ELFUTILS/include/elfutils/libdw.h" ] || {
    echo 'Set PREBUILTS and ELFUTILS to the pinned toolchains.' >&2; exit 2;
  }
}
require_prepared() {
  [ -f "$BUILD_ROOT/.sheng618-ready.json" ] || { echo 'Run bash buildkernel.sh first.' >&2; exit 2; }
}
require_kernel() {
  require_prepared
  [ -f "$output/.kernel-ready.json" ] || { echo 'Run bash buildkernel.sh first.' >&2; exit 2; }
  [ "$(sha256sum "$PROJECT_ROOT/sheng_defconfig" | cut -d' ' -f1)" = "$(jq -r .defconfig_sha256 "$output/.kernel-ready.json")" ] || {
    echo 'sheng_defconfig changed; rerun buildkernel.sh.' >&2; exit 2;
  }
  [ "$(sha256sum "$output/kernel.config" | cut -d' ' -f1)" = "$(jq -r .kernel_config_sha256 "$output/.kernel-ready.json")" ] || {
    echo 'Kernel configuration changed; rerun buildkernel.sh.' >&2; exit 2;
  }
  [ "$(sha256sum "$output/kernel-Image" | cut -d' ' -f1)" = "$(jq -r .kernel_image_sha256 "$output/.kernel-ready.json")" ] || {
    echo 'Core Image changed; rerun buildkernel.sh.' >&2; exit 2;
  }
}
run() {
  local label=$1
  shift
  echo "[$label]"
  if ! "$@" > "$output/$label.log" 2>&1; then tail -60 "$output/$label.log"; return 1; fi
}
invalidate_result() {
  rm -f -- "$output/build-result.json" "$output/boot.img" "$dist/build-result.json" "$dist/boot.img" "$dist/SHA256SUMS"
}
publish_result() {
  cp "$output/Image" "$output/build-result.json" "$dist/"
  if [ "$(jq -r .boot_packaged "$output/build-result.json")" = true ]; then cp "$output/boot.img" "$dist/"; fi
  (cd "$dist"; sha256sum Image build-result.json > SHA256SUMS
    if [ "$(jq -r .boot_packaged build-result.json)" = true ]; then sha256sum boot.img >> SHA256SUMS; fi)
}
