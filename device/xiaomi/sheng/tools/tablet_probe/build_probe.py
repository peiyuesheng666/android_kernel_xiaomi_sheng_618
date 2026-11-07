#!/usr/bin/env python3
"""Build the optional, ordinary-UID tablet probe; it is never part of the ROM."""
import argparse
import os
from pathlib import Path
import subprocess
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument("--rom", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = args.rom.resolve(strict=True)
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
for directory in ("classes", "dex"):
    (out / directory).mkdir(exist_ok=True)
source = Path(__file__).resolve().parent
jdk = root / "prebuilts/jdk/jdk21/linux-x86"
host = root / "out/host/linux-x86/bin"
sdk = root / "prebuilts/sdk/34/public/android.jar"
env = dict(os.environ, JAVA_HOME=str(jdk), PATH=str(jdk / "bin") + ":" + os.environ["PATH"], LC_ALL="C.UTF-8")
def run(command):
    subprocess.run([str(x) for x in command], cwd=root, env=env, check=True)
run([jdk / "bin/javac", "-source", "8", "-target", "8", "-classpath", sdk,
     "-d", out / "classes", *sorted(source.glob("*.java"))])
run([host / "d8", "--lib", sdk, "--min-api", "23", "--output", out / "dex",
     *sorted((out / "classes").rglob("*.class"))])
run([host / "aapt2", "link", "--manifest", source / "AndroidManifest.xml", "-I", sdk, "-o", out / "unsigned.apk"])
with zipfile.ZipFile(out / "unsigned.apk", "a", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.write(out / "dex/classes.dex", "classes.dex")
run([host / "zipalign", "-f", "4", out / "unsigned.apk", out / "aligned.apk"])
security = root / "build/make/target/product/security"
run([host / "apksigner", "sign", "--key", security / "testkey.pk8", "--cert",
     security / "testkey.x509.pem", "--out", out / "probe.apk", out / "aligned.apk"])
run([host / "apksigner", "verify", "--verbose", out / "probe.apk"])
print(out / "probe.apk")
