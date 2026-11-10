#!/usr/bin/env bash
# Upstream mkbootimg/avbtool utilities, called from the Bash build.
set -euo pipefail
image=$(realpath -- "${1:?Image}")
stock=$(realpath -- "${2:?Stock boot.img}")
output=$(realpath -- "${3:?Output directory}")
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python=${PYTHON:-python3.11}
"$python" "$here/mkbootimg/unpack_bootimg.py" --boot_img "$stock" --out "$output/stock-parts" > "$output/stock-boot-info.txt"
[ ! -s "$output/stock-parts/ramdisk" ] || { echo 'Unexpected stock boot ramdisk'; exit 1; }
header=$(sed -n 's/^boot image header version: //p' "$output/stock-boot-info.txt")
os_version=$(sed -n 's/^os version: //p' "$output/stock-boot-info.txt")
os_patch=$(sed -n 's/^os patch level: //p' "$output/stock-boot-info.txt")
[ "$header" = 4 ] || { cat "$output/stock-boot-info.txt"; exit 1; }
version_args=()
if [ -n "$os_version" ] && [ "$os_version" != None ]; then version_args+=(--os_version "$os_version"); fi
if [ -n "$os_patch" ] && [ "$os_patch" != None ]; then version_args+=(--os_patch_level "$os_patch"); fi
gzip -n -9 -c "$image" > "$output/Image.gz"
"$python" "$here/mkbootimg/mkbootimg.py" --kernel "$output/Image.gz" \
  --header_version "$header" "${version_args[@]}" \
  --cmdline loglevel=4 --output "$output/boot.img"
"$python" "$here/avbtool.py" add_hash_footer --image "$output/boot.img" \
  --partition_name boot --partition_size "$(stat -c %s "$stock")" --algorithm NONE
"$python" "$here/avbtool.py" verify_image --image "$output/boot.img"
