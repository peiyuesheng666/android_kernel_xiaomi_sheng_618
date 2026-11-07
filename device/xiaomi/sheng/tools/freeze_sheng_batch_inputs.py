#!/usr/bin/env python3
"""Freeze the completed r13 build and pinned bases without packaging or flashing."""
import argparse
import ctypes
import ctypes.util
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess
import tempfile

from package_sheng_batch_followup import (
    COLOR_DEVICE_INPUTS, DEVICE, FPC_ALIAS, FPC_TARGET_SHA256, PINNED, REQUIRED, load_spec,
)
from package_sheng_batch_helpers import (
    complete_metadata, erofs_input_keys, ext4_snapshot, inode_number, new_metadata,
    packaging_input_path, relative_path, run, sibling_symlink_target,
    validate_inputs, validate_packaging_inputs,
)
from package_sheng_model_followup import PRODUCT, ROM, sha
from package_sheng_overlay_followup import (
    ODM_BYTES, SYSTEM_BYTES, SYSTEM_DEFAULTS_BYTES, VBMETA_BYTES, VBMETA_SYSTEM_BYTES,
)

EXPECTED_OUTPUTS = dict(system=SYSTEM_BYTES, odm=ODM_BYTES, vendor=303517696,
                        vbmeta=VBMETA_BYTES, vbmeta_system=VBMETA_SYSTEM_BYTES)
PACKAGING_TOOLS = {
    'tools/' + name for name in (
        'freeze_sheng_batch_inputs.py', 'package_sheng_batch_followup.py',
        'package_sheng_batch_helpers.py', 'publish_sheng_batch_windows.ps1',
        'flash_sheng_batch_followup.ps1', 'test_sheng_batch_helpers.py',
        'test_sheng_batch_publication_fixture.py', 'package_sheng_model_followup.py',
        'package_sheng_overlay_followup.py', 'package_sheng_location_followup.py',
        'audit_erofs_metadata.py',
    )
}
DIRECT_SOURCES = {
    ('system', 'etc/device-config-defaults'): 'configs/device-config-defaults',
    ('vendor', 'etc/init/init.sm8550.rc'): 'rootdir/etc/init.sm8550.rc',
    ('vendor', 'etc/snapdragon_color_libs_config.xml'): 'configs/display/color/snapdragon_color_libs_config.xml',
    ('vendor', 'etc/df_default.xml'): 'configs/display/color/df_default.xml',
}


class SelabelOptions(ctypes.Structure):
    _fields_ = [('type', ctypes.c_int), ('value', ctypes.c_char_p)]


class CompiledContexts:
    """Look up labels from an exact snapshot of the frozen compiled text."""

    def __init__(self, contents):
        library = ctypes.util.find_library('selinux')
        if not library:
            raise RuntimeError('libselinux is required for compiled file-context lookup')
        self.lib = ctypes.CDLL(library, use_errno=True)
        self.lib.selabel_open.argtypes = [ctypes.c_uint, ctypes.POINTER(SelabelOptions), ctypes.c_uint]
        self.lib.selabel_open.restype = ctypes.c_void_p
        self.lib.selabel_lookup.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                                           ctypes.c_char_p, ctypes.c_int]
        self.lib.selabel_lookup.restype = ctypes.c_int
        self.lib.selabel_close.argtypes = [ctypes.c_void_p]
        self.lib.freecon.argtypes = [ctypes.c_void_p]
        self.temp = tempfile.TemporaryDirectory(prefix='sheng-freeze-contexts-')
        context_file = Path(self.temp.name) / 'file_contexts'
        context_file.write_bytes(contents)
        # SELABEL_CTX_FILE=0, SELABEL_OPT_PATH=3, SELABEL_OPT_BASEONLY=2.
        # The fresh directory has no .bin/.local files that could override the frozen text.
        options = (SelabelOptions * 2)(SelabelOptions(3, os.fsencode(context_file)),
                                      SelabelOptions(2, b'1'))
        self.handle = self.lib.selabel_open(0, options, len(options))
        if not self.handle:
            error = ctypes.get_errno()
            self.temp.cleanup()
            raise OSError(error, 'Unable to open the frozen compiled file contexts')

    def lookup(self, path, mode):
        context = ctypes.c_void_p()
        if self.lib.selabel_lookup(self.handle, ctypes.byref(context), os.fsencode(path), mode):
            raise OSError(ctypes.get_errno(), 'No compiled SELinux label for ' + path)
        try:
            value = ctypes.string_at(context).decode('ascii')
        finally:
            self.lib.freecon(context)
        # Compiled Qualcomm policy includes valid names such as vendor_diag-router_exec.
        assert re.fullmatch(r'u:object_r:[A-Za-z0-9_.-]+:s0', value), value
        return value

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.lib.selabel_close(self.handle)
        self.temp.cleanup()


def device_inputs(workspace):
    peer = workspace / 'device/xiaomi/sheng'
    tracked = subprocess.run(['git', '-C', str(peer), 'ls-files', '-z', '--', '.'],
                             check=True, capture_output=True).stdout.decode('utf-8').split('\0')
    paths = {relative_path(p) for p in tracked if p and PurePosixPath(p).parts[0] != 'docs'}
    paths |= {'Android.bp', 'device.mk', 'lineage_sheng.mk', 'rootdir/etc/init.sm8550.rc',
              'sepolicy/vendor/file_contexts', 'configs/device-config-defaults'}
    paths |= COLOR_DEVICE_INPUTS | PACKAGING_TOOLS
    overlay = DEVICE / 'overlay/FrameworkResOverlaySheng'
    assert overlay.is_dir() and not overlay.is_symlink()
    paths |= {str(p.relative_to(DEVICE)) for p in overlay.rglob('*') if p.is_file()}
    frozen = {}
    for relative in sorted(paths):
        source, reviewed = DEVICE / relative, peer / relative
        assert source.is_file() and not source.is_symlink(), source
        assert reviewed.is_file() and not reviewed.is_symlink(), reviewed
        assert source.resolve().is_relative_to(DEVICE.resolve())
        assert reviewed.resolve().is_relative_to(peer.resolve())
        digest = sha(source)
        assert sha(reviewed) == digest, f'Workspace and compiled device sources differ: {relative}'
        frozen[relative] = digest
    return frozen


def freeze_files(partition):
    entries = {}
    for relative in sorted(REQUIRED[partition]):
        source = PRODUCT / partition / relative
        assert source.resolve().is_relative_to((PRODUCT / partition).resolve()), source
        if source.is_symlink():
            assert partition == 'odm' and relative == FPC_ALIAS
            raw = os.readlink(source)
            target_relative = sibling_symlink_target(relative, raw)
            target = PRODUCT / partition / target_relative
            assert raw == 'fingerprint.fpc.so' and target.is_file() and not target.is_symlink()
            assert sha(target) == FPC_TARGET_SHA256
            encoded = raw.encode('utf-8')
            entries[relative] = dict(kind='symlink', source=str(source), link_target=raw,
                                     bytes=len(encoded), sha256=hashlib.sha256(encoded).hexdigest(),
                                     target_sha256=FPC_TARGET_SHA256)
        else:
            assert source.is_file() and not source.is_symlink(), source
            entries[relative] = dict(kind='file', source=str(source), bytes=source.stat().st_size,
                                     sha256=sha(source))
            direct = DIRECT_SOURCES.get((partition, relative))
            if direct:
                assert source.read_bytes() == (DEVICE / direct).read_bytes(), direct
                entries[relative]['device_source'] = direct
    validate_inputs(partition, entries, allow_symlinks=partition in ('odm', 'vendor'))
    return entries


def erofs_new_nodes(partition, base, entries, labels):
    metadata, _ = complete_metadata(base)
    assert metadata['']['type'] == stat.S_IFDIR
    timestamp = metadata['']['mtime_ns'] // 1_000_000_000 * 1_000_000_000
    # mkfs applies this same compiled context table to every inode. Refuse a label
    # change to any existing inode instead of disguising it as new-node metadata.
    for relative, inode in metadata.items():
        existing_label = bytes.fromhex(inode['xattrs']['6:selinux']).rstrip(b'\0').decode('ascii')
        assert labels.lookup('/' + partition + relative, inode['type']) == existing_label, \
            f'Compiled contexts would relabel an existing inode: {partition}{relative}'
    kinds = {}
    for relative, entry in entries.items():
        key = '/' + relative
        if key in metadata:
            assert entry['kind'] == 'file' and metadata[key]['type'] == stat.S_IFREG
            assert metadata[key]['nlink'] == 1, f'Hardlink replacement is forbidden: {relative}'
        else:
            kinds[relative] = stat.S_IFLNK if entry['kind'] == 'symlink' else stat.S_IFREG
        for parent in PurePosixPath(relative).parents:
            if str(parent) == '.':
                continue
            key = '/' + str(parent)
            if key in metadata:
                assert metadata[key]['type'] == stat.S_IFDIR, key
            else:
                assert kinds.get(str(parent), stat.S_IFDIR) == stat.S_IFDIR
                kinds[str(parent)] = stat.S_IFDIR
    result = {}
    for relative, kind in sorted(kinds.items()):
        mode = 0o755 if kind == stat.S_IFDIR else 0o777 if kind == stat.S_IFLNK else 0o644
        value = dict(uid=0, gid=0, mode=mode, mtime_ns=timestamp,
                     selinux=labels.lookup('/' + partition + '/' + relative, kind))
        new_metadata(value, directory=kind == stat.S_IFDIR, symlink=kind == stat.S_IFLNK)
        result[relative] = value
    return result


def system_new_nodes(base, entries, labels):
    assert set(entries) == {'etc/device-config-defaults'}
    source = PRODUCT / 'system/etc/device-config-defaults'
    assert source.read_bytes() == (DEVICE / 'configs/device-config-defaults').read_bytes() == SYSTEM_DEFAULTS_BYTES
    check = run(['debugfs', '-R', 'stat /system/etc/device-config-defaults', base],
                capture_output=True, text=True)
    assert 'File not found' in check.stderr, 'Pinned system base must not already contain the new defaults inode'
    snapshot = ext4_snapshot(base)
    inode = snapshot['inodes'][inode_number(base, '/system/etc')]
    assert stat.S_ISDIR(struct.unpack_from('<H', inode, 0)[0])
    seconds = struct.unpack_from('<I', inode, 12)[0]
    extra = struct.unpack_from('<I', inode, 136)[0]
    seconds += (extra & 3) << 32
    label = labels.lookup('/system/etc/device-config-defaults', stat.S_IFREG)
    assert label == 'u:object_r:system_file:s0', label
    value = dict(uid=0, gid=0, mode=0o644, mtime_ns=seconds * 1_000_000_000, selinux=label)
    new_metadata(value)
    return {'etc/device-config-defaults': value}


def verify_art_properties():
    text = (PRODUCT / 'vendor/build.prop').read_text()
    for key, expected in (('ro.zygote', 'zygote64'), ('dalvik.vm.dex2oat64.enabled', 'true')):
        values = [line.split('=', 1)[1] for line in text.splitlines() if line.startswith(key + '=')]
        assert values == [expected], f'Compiled vendor property must be uniquely {key}={expected}: {values}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    assert __debug__, 'Do not disable freezing assertions with Python -O'
    assert DEVICE.resolve() == (ROM / 'device/xiaomi/sheng').resolve(), \
        'Run the freezer from the compiled ROM device tree, after its build succeeds'
    workspace = args.workspace.resolve(strict=True)
    assert workspace.is_dir()
    assert not os.path.lexists(args.output), 'Never overwrite a frozen specification'
    output = args.output.resolve()
    assert output.suffix.lower() == '.json' and output.parent.is_dir()
    bases = {p: workspace / f'artifacts/system-hardware-followup-sheng-{release}/{p}.img'
             for p, (release, _) in PINNED.items()}
    for partition, base in bases.items():
        assert base.is_file() and not base.is_symlink() and sha(base) == PINNED[partition][1], partition
        if partition in EXPECTED_OUTPUTS:
            assert base.stat().st_size == EXPECTED_OUTPUTS[partition], partition
    verify_art_properties()
    frozen_device = device_inputs(workspace)
    build_keys = set().union(*(erofs_input_keys(p) for p in ('odm', 'vendor')))
    frozen_build = {key: sha(packaging_input_path(key)) for key in sorted(build_keys)}
    validate_packaging_inputs(REQUIRED, frozen_build)
    context_bytes = packaging_input_path('@sepolicy_file_contexts').read_bytes()
    assert hashlib.sha256(context_bytes).hexdigest() == frozen_build['@sepolicy_file_contexts']
    partitions = {}
    with CompiledContexts(context_bytes) as labels:
        for partition in sorted(REQUIRED):
            entries = freeze_files(partition)
            nodes = (system_new_nodes(bases[partition], entries, labels) if partition == 'system'
                     else erofs_new_nodes(partition, bases[partition], entries, labels))
            partitions[partition] = dict(files=entries, new_nodes=nodes)
    spec = dict(revision=13, partitions=partitions, device_inputs=frozen_device,
                build_inputs=frozen_build, expected_outputs=EXPECTED_OUTPUTS)
    # Validate in a private sibling file before exposing the requested final JSON.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent,
                                     prefix='.' + output.name + '-', suffix='.tmp', delete=False) as stream:
        staged = Path(stream.name)
        json.dump(spec, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    try:
        assert load_spec(staged) == spec
        for partition, base in bases.items():
            assert sha(base) == PINNED[partition][1], f'Baseline changed while freezing: {partition}'
        os.link(staged, output)  # Atomic creation; EEXIST never replaces an earlier specification.
    finally:
        staged.unlink()
    print(json.dumps(dict(revision=13, output=str(output), sha256=sha(output),
                          device_input_count=len(frozen_device), filesystem_partitions=sorted(partitions),
                          expected_outputs=EXPECTED_OUTPUTS), indent=2))


if __name__ == '__main__':
    main()
