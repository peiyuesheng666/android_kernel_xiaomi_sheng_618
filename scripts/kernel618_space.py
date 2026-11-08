#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read WSL capacity, including free space inside already allocated VHDX blocks.

VHDX BAT entries are read only. Reuse credit is allowed only for the current
registered WSL VHDX when its host file is neither sparse nor compressed.
The calculation subtracts every potentially occupied virtual byte. Retained
UNMAPPED blocks with valid file offsets can be rewritten inside this nonsparse
file, without growing its host allocation.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import uuid


BAT_GUID = '2dc27766-f623-4200-9d64-115e9bfd4a08'
METADATA_GUID = '8b7ca206-4790-4b9a-b8fe-575f050f886e'
PARAMETERS_GUID = 'caa16737-fa36-4d43-b3b6-33f0aa44e76b'
SIZE_GUID = '2fa54224-cd1b-4876-b211-5dbed83bf4b8'
SECTOR_GUID = '8141bf1d-a96f-4709-ba47-f233a8faab5f'


def crc32c(data):
    table = []
    for value in range(256):
        for _ in range(8):
            value = (value >> 1) ^ (0x82f63b78 if value & 1 else 0)
        table.append(value)
    value = 0xffffffff
    for byte in data:
        value = table[(value ^ byte) & 255] ^ (value >> 8)
    return value ^ 0xffffffff


def read_at(stream, offset, length):
    stream.seek(offset)
    data = stream.read(length)
    if len(data) != length:
        raise ValueError('Truncated VHDX data')
    return data


def vhdx_payload(path):
    file_size = path.stat().st_size
    with path.open('rb') as stream:
        if read_at(stream, 0, 8) != b'vhdxfile':
            raise ValueError('Not a VHDX file')
        regions = None
        for offset in (192 * 1024, 256 * 1024):
            data = bytearray(read_at(stream, offset, 64 * 1024))
            stored = struct.unpack_from('<I', data, 4)[0]
            data[4:8] = b'\0' * 4
            if data[:4] != b'regi' or crc32c(data) != stored:
                continue
            count = struct.unpack_from('<I', data, 8)[0]
            if count > 2047:
                raise ValueError('Invalid VHDX region count')
            regions = {}
            for i in range(count):
                start = 16 + 32 * i
                guid = str(uuid.UUID(bytes_le=bytes(data[start:start + 16])))
                region_offset, length = struct.unpack_from('<QI', data, start + 16)
                if region_offset + length > file_size:
                    raise ValueError('VHDX region exceeds host file')
                regions[guid] = (region_offset, length)
            break
        if not regions or BAT_GUID not in regions or METADATA_GUID not in regions:
            raise ValueError('No valid VHDX BAT/metadata region table')
        metadata_offset, metadata_length = regions[METADATA_GUID]
        metadata = read_at(stream, metadata_offset, metadata_length)
        if metadata[:8] != b'metadata':
            raise ValueError('Invalid VHDX metadata signature')
        count = struct.unpack_from('<H', metadata, 10)[0]
        entries = {}
        for i in range(count):
            start = 32 + i * 32
            guid = str(uuid.UUID(bytes_le=metadata[start:start + 16]))
            offset, length = struct.unpack_from('<II', metadata, start + 16)
            if offset + length > len(metadata):
                raise ValueError('VHDX metadata entry out of bounds')
            entries[guid] = metadata[offset:offset + length]
        block_size, flags = struct.unpack_from('<II', entries[PARAMETERS_GUID])
        virtual_size = struct.unpack('<Q', entries[SIZE_GUID])[0]
        sector_size = struct.unpack('<I', entries[SECTOR_GUID])[0]
        if flags & 2:
            raise ValueError('Differencing VHDX is not eligible for reuse credit')
        if sector_size not in (512, 4096) or block_size < 1024**2 or block_size > 256 * 1024**2 or block_size & (block_size - 1):
            raise ValueError('Unsupported VHDX block/sector size')
        block_count = (virtual_size + block_size - 1) // block_size
        chunk_ratio = (2**23 * sector_size) // block_size
        bat_offset, bat_length = regions[BAT_GUID]
        bat = read_at(stream, bat_offset, bat_length)
        states = Counter()
        backed = retained = 0
        physical_ranges = []
        for i in range(block_count):
            index = i + i // chunk_ratio
            entry = struct.unpack_from('<Q', bat, 8 * index)[0]
            state = entry & 7
            states[state] += 1
            if state in (3, 6) and entry >> 20:  # retained UNMAPPED or FULLY_PRESENT
                physical_offset = (entry >> 20) << 20
                if physical_offset < 1024**2 or physical_offset + block_size > file_size:
                    raise ValueError('Fully-present payload outside host file')
                size = min(block_size, virtual_size - i * block_size)
                physical_ranges.append((physical_offset, physical_offset + block_size))
                if state == 6:
                    backed += size
                else:
                    retained += size
        physical_ranges.sort()
        if any(right[0] < left[1] for left, right in zip(physical_ranges, physical_ranges[1:])):
            raise ValueError('VHDX retained/present payload ranges overlap')
        if backed > file_size:
            raise ValueError('VHDX backed payload exceeds host file length')
        return {'virtual_bytes': virtual_size, 'host_file_bytes': file_size,
                'payload_block_bytes': block_size, 'fully_present_payload_bytes': backed,
                'retained_unmapped_payload_bytes': retained,
                'host_reserved_payload_bytes': backed + retained,
                'payload_state_counts': dict(states), 'region_crc32c_verified': True}


def current_vhd():
    distro = os.environ.get('WSL_DISTRO_NAME')
    if not distro:
        raise ValueError('No current WSL distribution identity')
    distro_literal = "'" + distro.replace("'", "''") + "'"
    script = (
        "$taskDistro=Get-ChildItem 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Lxss' | "
        "ForEach-Object {Get-ItemProperty -LiteralPath $_.PSPath} | "
        f"Where-Object {{$_.DistributionName -eq {distro_literal}}}; "
        "if(@($taskDistro).Count -ne 1){throw 'No unique registered WSL distro'}; "
        "$taskName=$taskDistro.VhdFileName; if(-not $taskName){$taskName='ext4.vhdx'}; "
        "$taskPath=[IO.Path]::Combine($taskDistro.BasePath,$taskName); "
        "$taskFile=Get-Item -LiteralPath $taskPath; "
        "$taskDrive=[IO.DriveInfo]::new([IO.Path]::GetPathRoot($taskFile.FullName)); "
        "[pscustomobject]@{distro=$taskDistro.DistributionName;path=$taskFile.FullName;"
        "attributes=[int]$taskFile.Attributes;host_available_bytes=$taskDrive.AvailableFreeSpace}|ConvertTo-Json -Compress"
    )
    data = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                          check=True, capture_output=True, text=True, encoding='utf-8').stdout
    descriptor = json.loads(data)
    if descriptor['attributes'] & (512 | 2048 | 16384):
        raise ValueError('Sparse/compressed/encrypted host VHDX: no reuse credit')
    host_path = descriptor['path'].removeprefix('\\\\?\\')
    if len(host_path) < 3 or host_path[1:3] != ':\\':
        raise ValueError('Unsupported WSL backing file location')
    descriptor['linux_path'] = '/mnt/' + host_path[0].lower() + '/' + host_path[3:].replace('\\', '/')
    descriptor['host_mount'] = '/mnt/' + host_path[0].lower()
    return descriptor


def probe_space(root):
    root = Path(root).resolve()
    ancestor = root
    while not ancestor.exists():
        ancestor = ancestor.parent
    stats = os.statvfs(ancestor)
    available = stats.f_bavail * stats.f_frsize
    privileged_free = (stats.f_bfree if os.geteuid() == 0 else stats.f_bavail) * stats.f_frsize
    result = {'schema': 1, 'root': str(root), 'linux_available_bytes': available,
              'linux_usable_free_bytes': privileged_free, 'already_backed_free_lower_bound_bytes': 0,
              'probe_read_only': True, 'probe_warnings': []}
    try:
        descriptor = current_vhd()
        vhd = vhdx_payload(Path(descriptor['linux_path']))
        source = subprocess.run(['findmnt', '-n', '-o', 'SOURCE', '--target', str(ancestor)],
                                check=True, capture_output=True, text=True).stdout.strip()
        device_size = int(subprocess.run(['lsblk', '-b', '-n', '-d', '-o', 'SIZE', source],
                                        check=True, capture_output=True, text=True).stdout.strip())
        if device_size != vhd['virtual_bytes']:
            raise ValueError('Root block device does not match registered VHDX virtual size')
        host_free = descriptor['host_available_bytes']
        # All virtual bytes outside usable filesystem free space are treated
        # as occupied, including ext4 metadata, reserved space for non-root,
        # unallocated areas and any regions outside this filesystem.
        backed_free = max(0, vhd['host_reserved_payload_bytes'] - (vhd['virtual_bytes'] - privileged_free))
        backed_free = min(backed_free, privileged_free)
        result.update(backing_vhdx=descriptor, vhdx=vhd, root_block_device=source,
                      host_free_bytes=host_free,
                      already_backed_free_lower_bound_bytes=backed_free,
                      effective_write_budget_bytes=min(privileged_free, host_free + backed_free))
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, struct.error) as error:
        host_free = shutil.disk_usage('/mnt/c').free if Path('/mnt/c').exists() else available
        result.update(host_free_bytes=host_free, effective_write_budget_bytes=min(available, host_free))
        result['probe_warnings'].append(str(error))
    for name in ('linux_available', 'linux_usable_free', 'host_free', 'already_backed_free_lower_bound', 'effective_write_budget'):
        result[name + '_gib'] = round(result[name + '_bytes'] / 1024**3, 2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/root/sheng-618'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = probe_space(args.root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
