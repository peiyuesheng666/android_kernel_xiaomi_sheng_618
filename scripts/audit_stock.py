#!/usr/bin/env python3
"""Unpack stock boot images using Google's tool; never modify the firmware."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

PROJECT = Path(__file__).resolve().parents[1]
WORK = Path("/root/sheng-612")
DEFAULT = "/mnt/e/6/玩机资源/XiaomiPad6SPro12.4刷机资源/sheng_images_OS3.0.303.0.WNXCNXM_16.0/images"

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", type=Path, default=Path(DEFAULT))
    args = parser.parse_args()
    unpacker = WORK / "tools/mkbootimg/unpack_bootimg.py"
    records = {}
    for name in ("boot", "vendor_boot", "init_boot", "recovery"):
        source = args.images / f"{name}.img"
        out = WORK / "stock" / name
        out.mkdir(parents=True, exist_ok=True)
        command = ["python3", str(unpacker), "--boot_img", str(source), "--out", str(out)]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        (out / "header.txt").write_text(result.stdout)
        records[name] = {"input": str(source), "sha256": sha256(source), "bytes": source.stat().st_size,
                         "header": result.stdout, "files": [p.name for p in out.iterdir()]}
        print(f"{name}: {result.stdout.strip()}")
    image = (WORK / "stock/boot/kernel").read_bytes()
    compression = "uncompressed"
    if image[:2] == b"\x1f\x8b":
        image = gzip.decompress(image)
        compression = "gzip"
    elif image[:4] in (b"\x02\x21\x4c\x18", b"\x04\x22\x4d\x18"):
        image = subprocess.run(["lz4", "-dc", str(WORK / "stock/boot/kernel")], capture_output=True, check=True).stdout
        compression = "lz4"
    (WORK / "stock/boot/Image.stock").write_bytes(image)
    banners = re.findall(rb"Linux version [^\x00\n]{1,500}", image)
    records["kernel"] = {"compression": compression, "uncompressed_bytes": len(image),
                          "banners": [s.decode(errors="replace") for s in banners]}
    start = image.find(b"IKCFG_ST")
    if start >= 0:
        import zlib
        config = zlib.decompress(image[start + 8:], wbits=31)
        (WORK / "stock/boot/stock.config").write_bytes(config)
        records["kernel"]["config"] = str(WORK / "stock/boot/stock.config")
    print(json.dumps(records["kernel"], indent=2))
    (PROJECT / "reports").mkdir(exist_ok=True)
    (PROJECT / "reports/stock-boot.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

if __name__ == "__main__":
    main()
