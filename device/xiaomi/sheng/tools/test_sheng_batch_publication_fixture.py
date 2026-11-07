#!/usr/bin/env python3
"""Tiny publication fixtures on explicitly selected mounts; no production inputs."""
import argparse
import errno
import json
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
        request = dict(root=helpers.windows_path(self.root), link=helpers.windows_path(link),
                       target=helpers.windows_path(self.root / (link.name + '-missing-target')))
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
        request = dict(source=helpers.windows_path(self.stage), destination=helpers.windows_path(self.destination))
        result = helpers.run([helpers.shutil.which('powershell.exe'), '-NoProfile', '-NonInteractive',
                              '-ExecutionPolicy', 'Bypass', '-File', helpers.windows_path(primitive)],
                             input=json.dumps(request).encode(), capture_output=True)
        response = json.loads(result.stdout.decode('utf-8-sig'))
        self.assertTrue(response['rejected'])
        self.assertIn(response['win32_error'], (80, 183))
        self.assertEqual(list(self.destination.iterdir()), [])
        self.assertEqual((self.stage / 'sentinel').read_bytes(), b'source')

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
    args = parser.parse_args()
    PARENT = args.parent.resolve(strict=True)
    assert PARENT.is_dir()
    mount = subprocess.run(['findmnt', '-T', str(PARENT), '-o', 'TARGET,SOURCE,FSTYPE,OPTIONS'],
                           check=True, capture_output=True, text=True)
    WINDOWS_MOUNT = 'aname=drvfs' in mount.stdout
    print(json.dumps({'fixture_parent': str(PARENT), 'mount': mount.stdout.strip(),
                      'expected_method': 'windows-directory-move' if WINDOWS_MOUNT else 'linux-renameat2-noreplace'}), flush=True)
    unittest.main(argv=[__file__], verbosity=2)
