#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
rom=/root/sheng-lineage/lineage-24.0
[[ -d "$rom/.repo/manifests.git" ]]
mkdir -p "$rom/.repo/local_manifests" "$rom/device/xiaomi/sheng"
cp -- "$here/manifests/sheng.xml" "$rom/.repo/local_manifests/sheng.xml"
# Only our own device directory is populated, without deleting existing files.
cp -a -- "$here/device/xiaomi/sheng/." "$rom/device/xiaomi/sheng/"
echo 'Installed sheng configuration and official LineageOS dependencies'
