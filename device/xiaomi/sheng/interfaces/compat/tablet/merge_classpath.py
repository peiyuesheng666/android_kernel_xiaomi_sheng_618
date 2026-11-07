#!/usr/bin/env python3
"""Append the device jar to an unmodified generated classpaths.proto fragment."""
import argparse
from pathlib import Path

JAR = b"/system_ext/framework/sheng-tablet-compat.jar"


def varint(value):
    encoded = bytearray()
    while value > 127:
        encoded.append((value & 127) | 128)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def merge(base):
    # ExportedClasspathsJars is repeated Jar jars=1. Jar uses path=1 and
    # classpath=2. Appending messages preserves every original field verbatim,
    # including SDK bounds and unknown fields added by another ROM version.
    if not base or JAR in base:
        raise ValueError("Missing base fragment or duplicate device jar")
    result = base
    for classpath in (1, 3):  # BOOTCLASSPATH and DEX2OATBOOTCLASSPATH
        entry = b"\x0a" + varint(len(JAR)) + JAR + b"\x10" + varint(classpath)
        result += b"\x0a" + varint(len(entry)) + entry
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_bytes(merge(args.base.read_bytes()))


if __name__ == "__main__":
    main()
