#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C LANG=C
log=/root/sheng-lineage/logs/dependencies.log
mkdir -p "$(dirname "$log")"
exec > >(tee -a "$log") 2>&1
apt-get update
apt-get install -y --no-install-recommends \
    bc bison build-essential ca-certificates ccache cpio curl device-tree-compiler \
    erofs-utils file flex fontconfig g++-multilib gcc-multilib git git-lfs gnupg gperf \
    imagemagick lib32ncurses-dev lib32readline-dev lib32z1-dev libc6-dev-i386 \
    libelf-dev libgl1-mesa-dev liblz4-tool libncurses5 libncurses-dev libssl-dev libx11-dev libxml2-utils lz4 \
    lzop openjdk-11-jdk-headless patchelf pngcrush python3 python3-pip \
    python3-protobuf python3-requests python3-setuptools python3-venv \
    rsync schedtool squashfs-tools unzip wget x11proto-core-dev xsltproc xz-utils zip zlib1g-dev zstd
command -v repo
git lfs version
java -version
dpkg-query -W -f='${Package}\t${Version}\n' > /root/sheng-lineage/logs/installed-packages.tsv
echo 'Host dependencies installed; Android uses its manifest-pinned JDK and Clang.'
