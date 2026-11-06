#!/usr/bin/env python3
"""Read official Gitiles metadata without syncing an Android workspace."""
import base64
import concurrent.futures
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
QUERIES = {
    "ack_head": "https://android.googlesource.com/kernel/common/+/refs/heads/android16-6.12?format=JSON",
    "manifest_head": "https://android.googlesource.com/kernel/manifest/+/refs/heads/common-android16-6.12?format=JSON",
    "clang_tree": "https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+/refs/heads/main-kernel-2025/?format=JSON",
    "rust_tree": "https://android.googlesource.com/platform/prebuilts/rust/+/refs/heads/main-kernel-2025/linux-x86/?format=JSON",
    "ack_constants": "https://android.googlesource.com/kernel/common/+/refs/heads/android16-6.12/build.config.constants?format=TEXT",
    "ack_version": "https://android.googlesource.com/kernel/common/+/refs/heads/android16-6.12/Makefile?format=TEXT",
}

def read(item):
    name, url = item
    with urllib.request.urlopen(url, timeout=45) as r:
        data = r.read().decode()
    if "format=TEXT" in url:
        data = base64.b64decode(data).decode()
        if name == "ack_version":
            data = "\n".join(data.splitlines()[:7])
    else:
        data = json.loads(data.removeprefix(")]}'\n"))
    return name, {"url": url, "data": data}

results = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for future in [pool.submit(read, item) for item in QUERIES.items()]:
        name, result = future.result()
        results[name] = result
        data = result["data"]
        if isinstance(data, dict) and "entries" in data:
            print(name, [entry["name"] for entry in data["entries"]])
        elif isinstance(data, dict):
            print(name, data.get("commit"), data.get("committer"))
        else:
            print(name, data)
(ROOT / "reports").mkdir(exist_ok=True)
(ROOT / "reports/source-probe.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
