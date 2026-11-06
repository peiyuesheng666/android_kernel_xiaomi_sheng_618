#!/usr/bin/env python3
"""Fetch only the pinned compiler directories required by the official ACK."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
import urllib.request

ROOT = Path("/root/sheng-612")
REPORTS = Path(__file__).resolve().parents[1] / "reports"
SPECS = [
    ("clang-r536225", "platform/prebuilts/clang/host/linux-x86", "clang-r536225"),
    ("rust-1.82.0.p2", "platform/prebuilts/rust", "linux-x86/1.82.0.p2"),
    ("kernel-build-tools", "kernel/prebuilts/build-tools", "linux-x86"),
    ("clang-tools", "platform/prebuilts/clang-tools", "linux-x86"),
]

def extract_archive(archive, destination):
    """Keep links inside this compiler; handle relative links explicitly.

    Ubuntu 22.04's backported tar data filter misresolves Gitiles' src/stdlibs
    symlink. Regular members still use the standard data filter.
    """
    destination = destination.resolve()
    with tarfile.open(archive) as tf:
        links = []
        for member in tf.getmembers():
            path = destination / member.name
            if not path.resolve().is_relative_to(destination):
                raise ValueError(f'Archive path escapes toolchain: {member.name}')
            if member.issym() or member.islnk():
                parent = path.parent if member.issym() else destination
                target = (parent / member.linkname).resolve()
                if not target.is_relative_to(destination):
                    raise ValueError(f'Archive link escapes toolchain: {member.name}')
                links.append((member, path, target))
        tf.extractall(destination, filter=lambda m, p: None if m.issym() or m.islnk() else tarfile.data_filter(m, p))
        for member, path, target in links:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink() or path.is_file():
                path.unlink()
            if member.issym():
                path.symlink_to(member.linkname)
            else:
                os.link(target, path)

def fetch(spec):
    name, project, subdir = spec
    base = f"https://android.googlesource.com/{project}"
    with urllib.request.urlopen(f"{base}/+/refs/heads/main-kernel-2025?format=JSON", timeout=45) as r:
        commit = json.loads(r.read().decode().removeprefix(")]}'\n"))["commit"]
    url = f"{base}/+archive/{commit}/{subdir}.tar.gz"
    archive = ROOT / "toolchains" / f"{name}.tar.gz"
    destination = ROOT / "toolchains" / name
    marker = destination / ".download-complete.json"
    if marker.is_file():
        print(f"Reusing completed official toolchain {name}", flush=True)
        return json.loads(marker.read_text())
    archive.parent.mkdir(parents=True, exist_ok=True)
    print(f"Preparing {name} from official commit {commit}", flush=True)
    if archive.exists():
        # Open and scan it once before reusing a download from an interrupted extraction.
        with tarfile.open(archive) as tf:
            tf.getmembers()
    else:
        subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--silent", "--show-error",
                        "--connect-timeout", "20", "--max-time", "1800", "--output", str(archive), url], check=True)
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    print(f"Extracting {name}: {archive.stat().st_size // 1048576} MiB", flush=True)
    destination.mkdir(exist_ok=True)
    extract_archive(archive, destination)
    result = {"name": name, "project": project, "revision": commit, "subdirectory": subdir,
              "url": url, "archive_sha256": digest.hexdigest(), "path": str(destination)}
    marker.write_text(json.dumps(result, indent=2))
    # The verified extracted directory is the build input; the archive is redundant.
    archive.unlink()
    print(f"Ready: {name}", flush=True)
    return result

parser = argparse.ArgumentParser()
parser.add_argument("--only", choices=[spec[0] for spec in SPECS])
args = parser.parse_args()
selected = [spec for spec in SPECS if not args.only or spec[0] == args.only]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    records = list(pool.map(fetch, selected))
REPORTS.mkdir(exist_ok=True)
record_file = REPORTS / "toolchains.json"
previous = json.loads(record_file.read_text()) if record_file.exists() else []
merged = {item["name"]: item for item in previous + records}
record_file.write_text(json.dumps(list(merged.values()), indent=2), encoding="utf-8")
