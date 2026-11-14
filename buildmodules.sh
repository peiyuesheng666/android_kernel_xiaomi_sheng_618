#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "${BASH_SOURCE[0]}")/scripts/build-env.sh"
if [ "${1:-}" = --help ]; then echo 'Usage: bash buildmodules.sh'; exit 0; fi
[ "$#" = 0 ] || { echo 'Usage: bash buildmodules.sh'; exit 2; }
start_stage buildmodules "$@"
require_toolchain
require_kernel
"$PYTHON" "$PROJECT_ROOT/scripts/apply-charging-fix.py"
"$PYTHON" "$PROJECT_ROOT/scripts/apply-repair-r85.py"
"$PYTHON" "$PROJECT_ROOT/scripts/apply-pen-stability.py"
"$PYTHON" "$PROJECT_ROOT/scripts/apply-factory-interfaces.py"
"$PYTHON" "$PROJECT_ROOT/scripts/apply-walt-compatibility.py"
invalidate_result
rm -f -- "$output/.modules-ready.json" "$output/.embed-ready.json"
# Restore the core configuration when rerunning this stage after embedding.
cp "$output/kernel.config" "$output/.config"
run modules-config "${make_cmd[@]}" olddefconfig
# Split BTF is tied to vmlinux even when module object files are unchanged.
# Regenerate the final .ko links before extracting this run's kernel BTF base.
"$PYTHON" "$PROJECT_ROOT/tools/invalidate-module-links.py"
run gki-modules "${make_cmd[@]}" modules
"$PYTHON" "$PROJECT_ROOT/tools/module-btf.py" extract --kernel "$output/vmlinux" --output "$output/kernel-module-base.btf"
awk -F '\t' '$3 == "vmlinux"' "$output/Module.symvers" | sort > "$output/kernel-symbols.before"
run soc "${make_cmd[@]}" "M=$soc" modules
run walt "${make_cmd[@]}" "M=$soc/kernel/sched/walt" modules "KBUILD_EXTRA_SYMBOLS=$soc/Module.symvers"
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
mapping=$PROJECT_ROOT/profiles/module-sources.json
rows=$output/module-build-hashes.tsv
: > "$rows"
while IFS=$'\t' read -r name source; do
  case "$source" in out/*) path=$output/${source#out/};; *) path=$K618/$source;; esac
  [ -f "$path" ] || { echo "Missing built module: $path"; exit 1; }
  printf '%s\t%s\n' "$name" "$(sha256sum "$path" | cut -d' ' -f1)" >> "$rows"
done < <(jq -r 'to_entries[] | [.key, .value] | @tsv' "$mapping")
[ "$(wc -l < "$rows")" = 345 ] || { echo 'Expected 345 modules'; exit 1; }
jq -n --arg symbols "$(sha256sum "$output/kernel-symbols.before" | cut -d' ' -f1)" \
  --arg hashes "$(sha256sum "$rows" | cut -d' ' -f1)" \
  --arg mapping "$(sha256sum "$mapping" | cut -d' ' -f1)" \
  '{module_count: 345, kernel_symbols_sha256: $symbols, module_hashes_sha256: $hashes, module_map_sha256: $mapping}' \
  > "$output/.modules-ready.json"
echo 'Built all 345 kernel modules.'
