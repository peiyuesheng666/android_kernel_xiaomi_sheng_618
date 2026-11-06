#!/usr/bin/env bash
set -euo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8
workspace=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
rom=/root/sheng-lineage/lineage-24.0
output=/root/sheng-lineage/audio-stereo-probe
mkdir -p "$output/classes" "$output/dex"
java_dir="$rom/prebuilts/jdk/jdk21/linux-x86/bin"
"$java_dir/javac" -source 8 -target 8 -classpath "$rom/prebuilts/sdk/current/public/android.jar" \
    -d "$output/classes" "$workspace/scripts/ShengStereoProbe.java"
"$java_dir/java" -cp "$rom/out/host/linux-x86/framework/d8.jar" com.android.tools.r8.D8 \
    --lib "$rom/prebuilts/sdk/current/public/android.jar" --min-api 35 \
    --output "$output/dex" "$output/classes/ShengStereoProbe.class"
(cd "$output/dex" && "$java_dir/jar" cf "$workspace/artifacts/audio-diagnostics-sheng/sheng-stereo-probe.jar" classes.dex)
