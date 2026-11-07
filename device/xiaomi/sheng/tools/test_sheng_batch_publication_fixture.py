#!/usr/bin/env python3
"""Tiny publication fixtures on explicitly selected mounts; no production inputs."""
import argparse
import errno
import json
import ntpath
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import package_sheng_batch_helpers as helpers


PARENT = None
WINDOWS_MOUNT = False
JUNCTION_TARGET_PARENT = None


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.sheng-publication-fixture-', dir=PARENT)
        self.root = Path(self.temp.name)
        self.outputs = {}
        for partition in ('system', 'vbmeta_system'):
            source = self.root / (partition + '-source.bin')
            source.write_bytes(partition.encode())
            self.outputs[partition] = source
        self.destination = self.root / 'published'
        self.stage = self.root / '.published-publishing'

    def tearDown(self):
        assert self.root.resolve().parent == PARENT.resolve()
        assert self.root.name.startswith('.sheng-publication-fixture-')
        self.temp.cleanup()

    def dangling_directory_link(self, link):
        if not WINDOWS_MOUNT:
            link.symlink_to(self.root / 'missing', target_is_directory=True)
            return
        fixture = self.root / 'create-dangling-junction.ps1'
        fixture.write_text("""$ErrorActionPreference = 'Stop'
$Reader = New-Object IO.StreamReader([Console]::OpenStandardInput(), [Text.Encoding]::UTF8)
$Request = $Reader.ReadToEnd() | ConvertFrom-Json
$Reader.Dispose()
$Root = [IO.Path]::GetFullPath($Request.root)
$Link = [IO.Path]::GetFullPath($Request.link)
$Target = [IO.Path]::GetFullPath($Request.target)
if ([IO.Path]::GetDirectoryName($Link) -ne $Root -or [IO.Path]::GetDirectoryName($Target) -ne $Root -or
    [IO.Directory]::Exists($Target) -or [IO.File]::Exists($Target)) { throw 'Paths must be new children of the dedicated fixture directory' }
[IO.Directory]::CreateDirectory($Target) | Out-Null
try { New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null }
catch {
    $ErrorCode = $_.Exception.GetBaseException().NativeErrorCode
    [Console]::Out.WriteLine((@{fixture_reparse_unavailable=$true; win32_error=$ErrorCode} | ConvertTo-Json -Compress))
    exit 3
}
finally { [IO.Directory]::Delete($Target) }
""")
        native_root = helpers.windows_path(self.root)
        request = dict(root=native_root, link=ntpath.join(native_root, link.name),
                       target=ntpath.join(native_root, link.name + '-missing-target'))
        try:
            helpers.run([helpers.shutil.which('powershell.exe'), '-NoProfile', '-NonInteractive',
                         '-ExecutionPolicy', 'Bypass', '-File', helpers.windows_path(fixture)],
                        input=json.dumps(request).encode(), capture_output=True)
        except subprocess.CalledProcessError as failure:
            if failure.returncode == 3:
                details = json.loads(failure.stdout.decode('utf-8-sig'))
                if details.get('fixture_reparse_unavailable') and details['win32_error'] in (1, 50, 1392):
                    self.skipTest(f'This volume rejects fixture reparse creation (Win32 {details["win32_error"]})')
            print(failure.stderr.decode('utf-8', errors='replace'), file=sys.stderr)
            raise

    def test_complete_batch_publication(self):
        with patch.object(helpers, 'windows_directory_move', wraps=helpers.windows_directory_move) as native:
            helpers.publish_batch(self.destination, self.outputs, {'fixture': True})
        self.assertEqual(native.call_count, int(WINDOWS_MOUNT))
        self.assertFalse(self.stage.exists())
        self.assertEqual(sorted(p.name for p in self.destination.iterdir()),
                         ['SHA256SUMS', 'build-result.json', 'system.img', 'vbmeta_system.img'])
        report = json.loads((self.destination / 'build-result.json').read_text())
        for item in report['files']:
            target = self.destination / item['name']
            self.assertEqual(helpers.sha(target), item['sha256'])
            self.assertEqual(target.stat().st_size, item['bytes'])

    def test_existing_destination_is_preserved(self):
        self.destination.mkdir()
        (self.destination / 'sentinel').write_bytes(b'preserved')
        with self.assertRaises(AssertionError):
            helpers.publish_batch(self.destination, self.outputs, {'fixture': True})
        self.assertFalse(self.stage.exists())
        self.assertEqual(sorted(p.name for p in self.destination.iterdir()), ['sentinel'])
        self.assertEqual((self.destination / 'sentinel').read_bytes(), b'preserved')

    def test_copy_failure_has_no_destination(self):
        copy = helpers.shutil.copyfile

        def fail_second(source, target):
            if Path(source).name.startswith('vbmeta_system'):
                raise OSError('Injected tiny-fixture copy failure')
            return copy(source, target)

        with patch.object(helpers.shutil, 'copyfile', side_effect=fail_second):
            with self.assertRaises(OSError):
                helpers.publish_batch(self.destination, self.outputs, {'fixture': True})
        self.assertFalse(self.destination.exists())
        self.assertTrue(self.stage.is_dir())
        self.assertEqual(sorted(p.name for p in self.stage.iterdir()), ['system.img'])

    def test_hash_failure_has_no_destination(self):
        copy = helpers.shutil.copyfile

        def corrupt_copy(source, target):
            result = copy(source, target)
            Path(target).write_bytes(b'x' * Path(source).stat().st_size)
            return result

        with patch.object(helpers.shutil, 'copyfile', side_effect=corrupt_copy):
            with self.assertRaises(AssertionError):
                helpers.publish_batch(self.destination, self.outputs, {'fixture': True})
        self.assertFalse(self.destination.exists())
        self.assertTrue(self.stage.is_dir())
        self.assertFalse((self.stage / 'build-result.json').exists())

    def test_dangling_destination_is_preserved(self):
        self.dangling_directory_link(self.destination)
        self.assertFalse(self.destination.exists())
        with self.assertRaises(AssertionError):
            helpers.publish_batch(self.destination, self.outputs, {'fixture': True})
        self.assertTrue(os.path.lexists(self.destination))
        self.assertFalse(self.stage.exists())

    def test_only_supported_errno_can_use_windows_fallback(self):
        for number in (errno.EINVAL, errno.ENOTSUP, errno.EPERM, errno.EIO, errno.EEXIST):
            with self.subTest(errno=number), \
                 patch.object(helpers, 'linux_rename_noreplace', side_effect=OSError(number, 'fixture')), \
                 patch.object(helpers, 'windows_directory_move') as native:
                if number in (errno.EINVAL, errno.ENOTSUP):
                    helpers.publish_directory(self.stage, self.destination)
                    native.assert_called_once_with(self.stage, self.destination)
                else:
                    with self.assertRaises(OSError):
                        helpers.publish_directory(self.stage, self.destination)
                    native.assert_not_called()

    def test_native_empty_destination_and_reparse_are_preserved(self):
        if not WINDOWS_MOUNT:
            self.skipTest('Native Windows validation requires drvfs')
        self.stage.mkdir()
        (self.stage / 'sentinel').write_bytes(b'source')
        for name, dangling in (('empty-target', False), ('reparse-target', True)):
            target = self.root / name
            if dangling:
                self.dangling_directory_link(target)
            else:
                target.mkdir()
            with self.subTest(target=name), self.assertRaises(subprocess.CalledProcessError):
                helpers.windows_directory_move(self.stage, target)
            self.assertTrue(os.path.lexists(target))
            self.assertEqual((self.stage / 'sentinel').read_bytes(), b'source')

    def test_native_paths_are_data(self):
        if not WINDOWS_MOUNT:
            self.skipTest('Native Windows validation requires drvfs')
        source = self.root / "source space [x] $(); '"
        destination = self.root / "final space [x] $(); '"
        source.mkdir()
        (source / 'sentinel').write_bytes(b'preserved')
        helpers.windows_directory_move(source, destination)
        self.assertFalse(source.exists())
        self.assertEqual((destination / 'sentinel').read_bytes(), b'preserved')

    def test_windows_fallback_destination_race_is_rejected(self):
        if not WINDOWS_MOUNT:
            self.skipTest('Native Windows validation requires drvfs')

        def create_destination_then_reject_linux(stage, destination):
            destination.mkdir()
            (destination / 'sentinel').write_bytes(b'preserved')
            raise OSError(errno.EINVAL, 'Injected unsupported Linux rename after target race')

        with patch.object(helpers, 'linux_rename_noreplace', side_effect=create_destination_then_reject_linux):
            with self.assertRaises(subprocess.CalledProcessError):
                helpers.publish_batch(self.destination, self.outputs, {'fixture': True})
        self.assertEqual(sorted(p.name for p in self.destination.iterdir()), ['sentinel'])
        self.assertEqual((self.destination / 'sentinel').read_bytes(), b'preserved')
        self.assertTrue((self.stage / 'SHA256SUMS').is_file())

    def test_native_directory_move_rejects_target_created_after_absence_check(self):
        if not WINDOWS_MOUNT:
            self.skipTest('Native Windows validation requires drvfs')
        self.stage.mkdir()
        (self.stage / 'sentinel').write_bytes(b'source')
        primitive = self.root / 'native-race-fixture.ps1'
        # The destination is deliberately created between the absence check and the same
        # native primitive used by production. No injection hook is added to production.
        primitive.write_text("""$ErrorActionPreference = 'Stop'
$Reader = New-Object IO.StreamReader([Console]::OpenStandardInput(), [Text.Encoding]::UTF8)
$Request = $Reader.ReadToEnd() | ConvertFrom-Json
$Reader.Dispose()
if ([IO.Directory]::Exists($Request.destination)) { throw 'Fixture destination must start absent' }
[IO.Directory]::CreateDirectory($Request.destination) | Out-Null
try {
    [IO.Directory]::Move($Request.source, $Request.destination)
    throw 'Unexpected native overwrite'
} catch [IO.IOException] {
    [Console]::Out.WriteLine((@{rejected=$true; win32_error=($_.Exception.HResult -band 65535)} | ConvertTo-Json -Compress))
}
""")
        native_root = helpers.windows_path(self.root)
        request = dict(source=ntpath.join(native_root, self.stage.name),
                       destination=ntpath.join(native_root, self.destination.name))
        result = helpers.run([helpers.shutil.which('powershell.exe'), '-NoProfile', '-NonInteractive',
                              '-ExecutionPolicy', 'Bypass', '-File', helpers.windows_path(primitive)],
                             input=json.dumps(request).encode(), capture_output=True)
        response = json.loads(result.stdout.decode('utf-8-sig'))
        self.assertTrue(response['rejected'])
        self.assertIn(response['win32_error'], (80, 183))
        self.assertEqual(list(self.destination.iterdir()), [])
        self.assertEqual((self.stage / 'sentinel').read_bytes(), b'source')

    def test_lexical_junction_parent_publishes_as_one_native_parent(self):
        if not WINDOWS_MOUNT or JUNCTION_TARGET_PARENT is None:
            self.skipTest('Requires a dedicated native Junction target parent')
        target_temp = tempfile.TemporaryDirectory(prefix='.sheng-junction-target-fixture-',
                                                   dir=JUNCTION_TARGET_PARENT)
        target = Path(target_temp.name)
        link = self.root / 'fixture-parent-junction'
        request = dict(source_root=helpers.windows_path(self.root),
                       target_parent=helpers.windows_path(JUNCTION_TARGET_PARENT),
                       link=ntpath.join(helpers.windows_path(self.root), link.name),
                       target=helpers.windows_path(target))
        validation = """$ErrorActionPreference = 'Stop'
$Reader = New-Object IO.StreamReader([Console]::OpenStandardInput(), [Text.Encoding]::UTF8)
$Request = $Reader.ReadToEnd() | ConvertFrom-Json
$Reader.Dispose()
$SourceRoot = [IO.Path]::GetFullPath($Request.source_root)
$TargetParent = [IO.Path]::GetFullPath($Request.target_parent)
$Link = [IO.Path]::GetFullPath($Request.link)
$Target = [IO.Path]::GetFullPath($Request.target)
if ([IO.Path]::GetDirectoryName($Link) -ne $SourceRoot -or [IO.Path]::GetFileName($Link) -ne 'fixture-parent-junction' -or
    [IO.Path]::GetDirectoryName($Target) -ne $TargetParent -or
    -not [IO.Path]::GetFileName($Target).StartsWith('.sheng-junction-target-fixture-') -or
    -not [IO.Directory]::Exists($SourceRoot) -or -not [IO.Directory]::Exists($Target) -or
    ([IO.File]::GetAttributes($SourceRoot) -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
    ([IO.File]::GetAttributes($Target) -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'Fixture paths must be allocated ordinary temporary directories and one direct child link'
}
"""
        def invoke(name, body):
            fixture = self.root / name
            fixture.write_text(validation + body)
            return helpers.run([helpers.shutil.which('powershell.exe'), '-NoProfile', '-NonInteractive',
                                '-ExecutionPolicy', 'Bypass', '-File', helpers.windows_path(fixture)],
                               input=json.dumps(request).encode(), capture_output=True)

        resolved_check = """$Item = Get-Item -LiteralPath $Link -Force
if ($Item.LinkType -ne 'Junction' -or ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {
    throw 'Fixture link is not a Junction'
}
$ResolvedTarget = [IO.Path]::GetFullPath(@($Item.Target)[0])
if (-not [string]::Equals($ResolvedTarget, $Target, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Refuse a Junction whose resolved target differs from the allocated fixture'
}
"""
        try:
            invoke('create-parent-junction.ps1', """foreach ($Entry in [IO.Directory]::EnumerateFileSystemEntries($SourceRoot)) {
    if ([IO.Path]::GetFileName($Entry) -eq [IO.Path]::GetFileName($Link)) { throw 'Fixture link already exists' }
}
New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null
""" + resolved_check)
            self.assertEqual(link.resolve(strict=True), target.resolve(strict=True))
            destination = link / 'published'
            observations = []
            native = helpers.windows_directory_move

            def observe_old_mapping(stage, final):
                old_source, old_final = helpers.windows_path(stage), helpers.windows_path(final)
                observations.append((old_source, old_final))
                self.assertNotEqual(ntpath.dirname(old_source).lower(), ntpath.dirname(old_final).lower())
                native(stage, final)

            with patch.object(helpers, 'windows_directory_move', side_effect=observe_old_mapping):
                helpers.publish_batch(destination, self.outputs, {'junction_fixture': True})
            self.assertEqual(len(observations), 1)
            for partition, source in self.outputs.items():
                self.assertEqual((target / 'published' / (partition + '.img')).read_bytes(), source.read_bytes())
                self.assertEqual((destination / (partition + '.img')).read_bytes(), source.read_bytes())
            self.assertFalse(os.path.lexists(link / '.published-publishing'))
            with self.assertRaises(AssertionError):
                helpers.publish_batch(destination, self.outputs, {'junction_fixture': True})

            race_destination = link / 'race-published'
            def competing_destination(stage, final):
                final.mkdir()
                (final / 'sentinel').write_bytes(b'preserved')
                raise OSError(errno.EINVAL, 'Injected Junction target race before fallback')
            with patch.object(helpers, 'linux_rename_noreplace', side_effect=competing_destination):
                with self.assertRaises(subprocess.CalledProcessError):
                    helpers.publish_batch(race_destination, self.outputs, {'junction_fixture': True})
            self.assertEqual(sorted(p.name for p in race_destination.iterdir()), ['sentinel'])
            self.assertEqual((race_destination / 'sentinel').read_bytes(), b'preserved')
        finally:
            if os.path.lexists(link):
                invoke('remove-parent-junction.ps1', resolved_check + """[IO.Directory]::Delete($Link)
if ([IO.Directory]::Exists($Link) -or -not [IO.Directory]::Exists($Target)) {
    throw 'Fixture cleanup must remove only the Junction and retain its target'
}
""")
            self.assertFalse(os.path.lexists(link))
            assert target.resolve().parent == JUNCTION_TARGET_PARENT.resolve()
            assert target.name.startswith('.sheng-junction-target-fixture-')
            target_temp.cleanup()

    def test_destination_race_is_rejected_by_renameat2(self):
        digest = helpers.sha
        final_image_checks = 0

        def create_destination_at_final_check(path):
            nonlocal final_image_checks
            if Path(path) == self.stage / 'vbmeta_system.img':
                final_image_checks += 1
                if final_image_checks == 2:
                    self.destination.mkdir()
                    (self.destination / 'sentinel').write_bytes(b'preserved')
            return digest(path)

        with patch.object(helpers, 'sha', side_effect=create_destination_at_final_check):
            with self.assertRaises(OSError) as failure:
                helpers.publish_batch(self.destination, self.outputs, {'fixture': True})
        self.assertEqual(failure.exception.errno, errno.EEXIST)
        self.assertEqual((self.destination / 'sentinel').read_bytes(), b'preserved')
        self.assertEqual(sorted(p.name for p in self.destination.iterdir()), ['sentinel'])
        self.assertTrue(self.stage.is_dir())
        self.assertTrue((self.stage / 'build-result.json').is_file())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--junction-target-parent', type=Path)
    args = parser.parse_args()
    PARENT = args.parent.absolute()
    if args.junction_target_parent:
        JUNCTION_TARGET_PARENT = args.junction_target_parent.resolve(strict=True)
    assert PARENT.is_dir()
    mount = subprocess.run(['findmnt', '-T', str(PARENT), '-o', 'TARGET,SOURCE,FSTYPE,OPTIONS'],
                           check=True, capture_output=True, text=True)
    WINDOWS_MOUNT = 'aname=drvfs' in mount.stdout
    print(json.dumps({'fixture_parent': str(PARENT), 'mount': mount.stdout.strip(),
                      'expected_method': 'windows-directory-move' if WINDOWS_MOUNT else 'linux-renameat2-noreplace'}), flush=True)
    unittest.main(argv=[__file__], verbosity=2)
