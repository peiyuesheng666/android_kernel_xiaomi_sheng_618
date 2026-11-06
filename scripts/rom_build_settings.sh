#!/usr/bin/env bash
# Latest user choice: all available CPUs and 80 GiB total runtime swap.
export SHENG_BUILD_JOBS=$(nproc)
export NINJA_HIGHMEM_NUM_JOBS=$SHENG_BUILD_JOBS
export USE_CCACHE=1
export CCACHE_EXEC=/usr/bin/ccache
export CCACHE_DIR=/root/sheng-lineage/ccache
export CCACHE_COMPRESS=true
mkdir -p "$CCACHE_DIR"
"$CCACHE_EXEC" --max-size=10G >/dev/null
export SOONG_ALLOW_MISSING_DEPENDENCIES=false
