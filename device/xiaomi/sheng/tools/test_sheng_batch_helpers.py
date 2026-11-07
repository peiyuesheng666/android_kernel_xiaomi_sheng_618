#!/usr/bin/env python3
"""Small synthetic filesystem/AVB tests; never read or update production images."""
import importlib
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import package_sheng_batch_helpers as helpers


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sheng-batch-fixture-')
        self.root = Path(self.temp.name)
        self.build = self.root / 'compiled'
        self.build.mkdir()
        self.product_patch = patch.object(helpers, 'PRODUCT', self.build)
        self.product_patch.start()
        sys.path.insert(0, str(helpers.ROM / 'external/avb'))
        self.avbtool = importlib.import_module('avbtool')
        self.avb = self.avbtool.Avb()

    def tearDown(self):
        self.product_patch.stop()
        assert self.root.resolve().parent == Path(tempfile.gettempdir()).resolve()
        self.temp.cleanup()

    def run_tool(self, arguments):
        return helpers.run(arguments, capture_output=True, text=True)

    def footer(self, image, partition, size):
        self.run_tool([helpers.HOST / 'avbtool', 'add_hashtree_footer', '--image', image,
                       '--partition_name', partition, '--partition_size', size,
                       '--hash_algorithm', 'sha256', '--salt', '01' * 32,
                       '--fec_num_roots', '2', '--algorithm', 'NONE', '--prop', 'fixture:unchanged'])

    def test_paths_fail_closed(self):
        for value in ('../etc/x', '/etc/x', 'a//b', 'a/./b', 'a;rm', 'a\n'):
            with self.assertRaises(AssertionError):
                helpers.relative_path(value)
        outside = self.root / 'outside'
        outside.mkdir()
        tree = self.root / 'tree'
        tree.mkdir()
        (tree / 'link').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(AssertionError):
            helpers.safe_target(tree, 'link/file')

    def test_optimized_python_is_rejected(self):
        result = subprocess.run([sys.executable, '-O', '-c', 'import package_sheng_batch_helpers'],
                                cwd=Path(__file__).parent, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('do not use -O', result.stderr)

    def test_ext4_add_and_replace_preserves_metadata(self):
        tree = self.root / 'fs-tree'
        (tree / 'etc').mkdir(parents=True)
        (tree / 'priv-app').mkdir()
        (tree / 'etc/keep').write_bytes(b'unchanged' * 1024)
        (tree / 'etc/policy.cil').write_bytes(b'old policy')
        base = self.root / 'baseline-system-ext.img'
        self.run_tool(['mke2fs', '-q', '-t', 'ext4', '-b', '4096', '-I', '256', '-N', '256',
                       '-O', '^has_journal,^metadata_csum,^64bit', '-d', tree, base, '4096'])
        self.footer(base, 'system_ext', 32 * 1024 * 1024)
        baseline_hash = helpers.sha(base)
        before_number = helpers.inode_number(base, '/etc/policy.cil')
        before_inode = helpers.ext4_snapshot(base)['inodes'][before_number]
        entries = {}
        for relative, content in (('etc/policy.cil', b'new policy' * 9000),
                                  ('priv-app/NewApp/config.xml', b'<fixture/>')):
            source = self.build / 'system_ext' / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(content)
            entries[relative] = dict(source=str(source), bytes=len(content), sha256=helpers.sha(source))
        meta = dict(uid=0, gid=0, mode=0o644, mtime_ns=1230768000 * 10**9,
                    selinux='u:object_r:system_file:s0')
        nodes = {'priv-app/NewApp': dict(meta, mode=0o755), 'priv-app/NewApp/config.xml': meta}
        work = self.root / 'stage'
        work.mkdir()
        image, descriptor, report = helpers.stage_ext4(
            'system_ext', base, entries, nodes, work, self.avb, self.avbtool, [])
        self.assertEqual(helpers.sha(base), baseline_hash)
        self.assertEqual(set(report['changed_files']), set(entries))
        self.assertEqual((work / 'system_ext-after/etc/keep').read_bytes(), (tree / 'etc/keep').read_bytes())
        after_inode = helpers.ext4_snapshot(image)['inodes'][helpers.inode_number(image, '/etc/policy.cil')]
        for start, end in ((0, 4), (8, 28), (32, 40), (100, 108), (112, 256)):
            self.assertEqual(before_inode[start:end], after_inode[start:end])
        self.assertEqual(descriptor.partition_name, 'system_ext')

    def test_erofs_add_and_replace_preserves_metadata_and_uuid(self):
        tree = self.root / 'erofs-tree'
        (tree / 'etc').mkdir(parents=True)
        (tree / 'etc/keep').write_bytes(b'unchanged' * 3000)
        (tree / 'etc/config.xml').write_bytes(b'old config')
        (tree / 'etc/link').symlink_to('keep')
        fake_rom = self.root / 'rom'
        context = fake_rom / 'out/soong/.intermediates/system/sepolicy/file_contexts.concat.tmp/android_common/gen/file_contexts.concat.tmp'
        context.parent.mkdir(parents=True)
        context.write_text('/vendor(/.*)? u:object_r:vendor_file:s0\n')
        context_bin = self.root / 'contexts.bin'
        self.run_tool([helpers.HOST / 'sefcontext_compile', '-o', context_bin, context])
        config = self.root / 'fs-config.txt'
        config.write_text(' 0 0 755 capabilities=0x0\nvendor/etc 0 0 755 capabilities=0x0\n'
                          'vendor/etc/keep 0 0 644 capabilities=0x0\n'
                          'vendor/etc/config.xml 0 0 644 capabilities=0x0\n'
                          'vendor/etc/link 0 0 777 capabilities=0x0\n')
        base = self.root / 'baseline-vendor.img'
        original_uuid = 'ff55b8ce-3b37-43f4-897a-208324b344be'
        self.run_tool([helpers.HOST / 'mkfs.erofs', '-z', 'lz4hc,9', '--mount-point', 'vendor',
                       '--fs-config-file', config, '--file-contexts', context_bin,
                       '-T', '1230768000', '-U', original_uuid, base, tree])
        self.footer(base, 'vendor', 8 * 1024 * 1024)
        baseline_hash = helpers.sha(base)
        info = self.build / 'obj/PACKAGING/vendor_intermediates/vendor_image_info.txt'
        info.parent.mkdir(parents=True)
        info.write_text('fs_type=ext4\nvendor_fs_type=erofs\navb_enable=true\n'
                        'vendor_disable_sparse=true\navb_avbtool=avbtool\n'
                        'avb_vendor_hashtree_enable=true\nerofs_default_compressor=lz4hc,9\n')
        entries = {}
        for relative, content in (('etc/config.xml', b'new config'),
                                  ('firmware/new/config.xml', b'<fixture/>')):
            source = self.build / 'vendor' / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(content)
            entries[relative] = dict(source=str(source), bytes=len(content), sha256=helpers.sha(source))
        meta = dict(uid=0, gid=0, mode=0o644, mtime_ns=1230768000 * 10**9,
                    selinux='u:object_r:vendor_file:s0')
        nodes = {p: dict(meta, mode=0o755) for p in ('firmware', 'firmware/new')}
        nodes['firmware/new/config.xml'] = meta
        # The AON alias resolves within the installed Android filesystem; the
        # host's /odm must never be followed while validating or extracting it.
        alias = 'lib64/camera/aon_front.pb'
        raw = '/odm/' + alias
        blob = self.build / 'odm' / alias
        blob.parent.mkdir(parents=True)
        blob.write_bytes(b'unchanged stock sensor protobuf')
        link = self.build / 'vendor' / alias
        link.parent.mkdir(parents=True)
        link.symlink_to(raw)
        entries[alias] = dict(kind='symlink', source=str(link), bytes=len(raw),
                             sha256=hashlib.sha256(raw.encode()).hexdigest(),
                             link_target=raw, target_sha256=helpers.sha(blob))
        nodes.update({p: dict(meta, mode=0o755) for p in ('lib64', 'lib64/camera')})
        nodes[alias] = dict(meta, mode=0o777)
        work = self.root / 'erofs-stage'
        work.mkdir()
        with patch.object(helpers, 'ROM', fake_rom):
            try:
                image, descriptor, report = helpers.stage_erofs(
                    'vendor', base, entries, nodes, work, self.avb, self.avbtool,
                    external_symlink_targets={raw: helpers.sha(blob)})
            except Exception:
                log = work / 'vendor-build.log'
                if log.exists():
                    print(log.read_text(), file=sys.stderr)
                candidate = work / 'vendor.img'
                if candidate.exists():
                    print('Baseline metadata:', helpers.complete_metadata(base), file=sys.stderr)
                    print('Candidate metadata:', helpers.complete_metadata(candidate), file=sys.stderr)
                raise
        self.assertEqual(helpers.sha(base), baseline_hash)
        self.assertEqual(helpers.complete_metadata(image)[1], original_uuid)
        self.assertEqual(set(report['changed_files']), set(entries))
        self.assertEqual((work / 'vendor-readback/etc/keep').read_bytes(), b'unchanged' * 3000)
        self.assertEqual(descriptor.partition_name, 'vendor')
        self.assertEqual(os.readlink(work / 'vendor-readback' / alias), raw)
        self.assertEqual(helpers.complete_metadata(image)[0]['/' + alias]['type'], stat.S_IFLNK)

    def test_cross_partition_alias_is_exactly_scoped(self):
        self.assertEqual(helpers.installed_symlink_target(
            'vendor', 'lib64/camera/aon_front.pb', '/odm/lib64/camera/aon_front.pb'),
            ('odm', 'lib64/camera/aon_front.pb'))
        for partition, relative, raw in (
            ('odm', 'lib64/camera/aon_front.pb', '/odm/lib64/camera/aon_front.pb'),
            ('vendor', 'lib64/camera/other.pb', '/odm/lib64/camera/aon_front.pb'),
            ('vendor', 'lib64/camera/aon_front.pb', '/odm/lib64/camera/other.pb'),
            ('vendor', 'lib64/camera/aon_front.pb', '../../odm/aon_front.pb'),
        ):
            with self.assertRaises(AssertionError):
                helpers.installed_symlink_target(partition, relative, raw)

    def test_system_prefix_addition(self):
        tree = self.root / 'system-tree'
        (tree / 'system/etc').mkdir(parents=True)
        (tree / 'system/etc/keep').write_bytes(b'unchanged')
        base = self.root / 'baseline-system.img'
        self.run_tool(['mke2fs', '-q', '-t', 'ext4', '-b', '4096', '-I', '256', '-N', '256',
                       '-O', '^has_journal,^metadata_csum,^64bit', '-d', tree, base, '2048'])
        self.footer(base, 'system', 16 * 1024 * 1024)
        relative = 'etc/device-config-defaults'
        source = self.build / 'system' / relative
        source.parent.mkdir(parents=True)
        source.write_bytes(b'fixture=enabled\n')
        entry = dict(source=str(source), bytes=source.stat().st_size, sha256=helpers.sha(source))
        meta = dict(uid=0, gid=0, mode=0o644, mtime_ns=1230768000 * 10**9,
                    selinux='u:object_r:system_file:s0')
        work = self.root / 'system-stage'
        work.mkdir()
        _, _, report = helpers.stage_ext4('system', base, {relative: entry}, {relative: meta},
                                         work, self.avb, self.avbtool, [])
        self.assertEqual(report['changed_files'], ['system/' + relative])
        self.assertEqual((work / 'system-after/system/etc/device-config-defaults').read_bytes(), source.read_bytes())
        self.assertEqual((work / 'system-after/system/etc/keep').read_bytes(), b'unchanged')

    def alias_fixture(self, existing=False, mismatched=False):
        relative = 'lib64/hw/fingerprint.fpc.default.so'
        target_relative = 'lib64/hw/fingerprint.fpc.so'
        raw = 'fingerprint.fpc.so'
        payload = b'original blob bytes' * 1500
        tree = self.root / 'odm-tree'
        (tree / 'lib64/hw').mkdir(parents=True)
        (tree / target_relative).write_bytes(b'different baseline blob' if mismatched else payload)
        if existing:
            (tree / relative).symlink_to(raw)
        fake_rom = self.root / 'rom'
        context = fake_rom / helpers.SEPOLICY_CONTEXTS
        context.parent.mkdir(parents=True)
        context.write_text('/odm(/.*)? u:object_r:vendor_file:s0\n')
        context_bin = self.root / 'alias-contexts.bin'
        self.run_tool([helpers.HOST / 'sefcontext_compile', '-o', context_bin, context])
        config = self.root / 'alias-fs-config.txt'
        config.write_text(' 0 0 755 capabilities=0x0\nodm/lib64 0 0 755 capabilities=0x0\n'
                          'odm/lib64/hw 0 2000 755 capabilities=0x0\n'
                          'odm/lib64/hw/fingerprint.fpc.so 1000 2000 644 capabilities=0x0\n' +
                          ('odm/' + relative + ' 0 0 777 capabilities=0x0\n' if existing else ''))
        base = self.root / 'baseline-odm.img'
        self.run_tool([helpers.HOST / 'mkfs.erofs', '-z', 'lz4hc,9', '--mount-point', 'odm',
                       '--fs-config-file', config, '--file-contexts', context_bin, '-T', '1230768000',
                       '-U', 'ff55b8ce-3b37-43f4-897a-208324b344be', base, tree])
        self.footer(base, 'odm', 8 * 1024 * 1024)
        info = self.build / 'obj/PACKAGING/odm_intermediates/odm_image_info.txt'
        info.parent.mkdir(parents=True)
        info.write_text('fs_type=ext4\nodm_fs_type=erofs\nerofs_default_compressor=lz4hc,9\n')
        target = self.build / 'odm' / target_relative
        target.parent.mkdir(parents=True)
        target.write_bytes(payload)
        source = self.build / 'odm' / relative
        source.symlink_to(raw)
        entry = dict(kind='symlink', source=str(source), link_target=raw, bytes=len(raw.encode()),
                     sha256=hashlib.sha256(raw.encode()).hexdigest(), target_sha256=helpers.sha(target))
        meta = dict(uid=0, gid=0, mode=0o777, mtime_ns=1230768000 * 10**9,
                    selinux='u:object_r:vendor_file:s0')
        return base, fake_rom, relative, target_relative, source, target, entry, meta

    def test_erofs_new_real_symlink_preserves_original_blob(self):
        base, fake_rom, relative, target_relative, source, target, entry, meta = self.alias_fixture()
        baseline_hash = helpers.sha(base)
        old_metadata, old_uuid = helpers.complete_metadata(base)
        work = self.root / 'alias-stage'
        work.mkdir()
        with patch.object(helpers, 'ROM', fake_rom):
            image, _, report = helpers.stage_erofs('odm', base, {relative: entry}, {relative: meta},
                                                   work, self.avb, self.avbtool)
        readback = work / 'odm-readback'
        self.assertTrue((readback / relative).is_symlink())
        self.assertEqual(os.readlink(readback / relative), os.readlink(source))
        self.assertEqual((readback / target_relative).read_bytes(), target.read_bytes())
        new_metadata, new_uuid = helpers.complete_metadata(image)
        self.assertEqual(new_metadata['/' + target_relative], old_metadata['/' + target_relative])
        self.assertEqual(new_metadata['/' + relative]['type'], stat.S_IFLNK)
        self.assertEqual(new_uuid, old_uuid)
        self.assertEqual(helpers.sha(base), baseline_hash)
        self.assertEqual(set(report['created_symlinks']), {relative})

    def test_alias_inputs_fail_closed_and_ext4_rejects_links(self):
        _, _, relative, _, source, target, entry, _ = self.alias_fixture()
        for raw in ('../fingerprint.fpc.so', '/fingerprint.fpc.so', 'sub/fpc.so', '.', '..'):
            with self.subTest(link=raw), self.assertRaises(AssertionError):
                helpers.sibling_symlink_target(relative, raw)
        for changed in (dict(entry, bytes=entry['bytes'] + 1), dict(entry, sha256='0' * 64),
                        dict(entry, link_target='other.so'), dict(entry, target_sha256='0' * 64)):
            with self.subTest(entry=changed), self.assertRaises(AssertionError):
                helpers.validate_inputs('odm', {relative: changed}, allow_symlinks=True)
        with self.assertRaises(AssertionError):
            helpers.validate_inputs('odm', {relative: entry})
        other = target.with_name('other.so')
        other.write_bytes(target.read_bytes())
        source.unlink()
        source.symlink_to('other.so')
        with self.assertRaises(AssertionError):
            helpers.validate_inputs('odm', {relative: entry}, allow_symlinks=True)
        source.unlink()
        source.symlink_to(entry['link_target'])
        ext4_target = self.build / 'system_ext/lib64/hw/fingerprint.fpc.so'
        ext4_target.parent.mkdir(parents=True)
        ext4_target.write_bytes(target.read_bytes())
        ext4_source = ext4_target.with_name('fingerprint.fpc.default.so')
        ext4_source.symlink_to(entry['link_target'])
        work = self.root / 'ext4-reject-alias'
        work.mkdir()
        with self.assertRaises(AssertionError):
            helpers.stage_ext4('system_ext', self.root / 'unused.img',
                               {relative: dict(entry, source=str(ext4_source))}, {}, work,
                               self.avb, self.avbtool, [])
        self.assertFalse((work / 'system_ext.img').exists())
        original = target.read_bytes()
        target.write_bytes(b'changed original blob')
        with self.assertRaises(AssertionError):
            helpers.validate_inputs('odm', {relative: entry}, allow_symlinks=True)
        target.write_bytes(original)
        source.unlink()
        source.write_bytes(original)
        with self.assertRaises(AssertionError):
            helpers.validate_inputs('odm', {relative: entry}, allow_symlinks=True)
        source.unlink()
        source.symlink_to('/tmp/outside-partition')
        with self.assertRaises(AssertionError):
            helpers.validate_inputs('odm', {relative: entry}, allow_symlinks=True)

    def test_erofs_existing_alias_is_not_replaced(self):
        base, fake_rom, relative, _, _, _, entry, meta = self.alias_fixture(existing=True)
        baseline_hash = helpers.sha(base)
        work = self.root / 'existing-alias-stage'
        work.mkdir()
        with patch.object(helpers, 'ROM', fake_rom), self.assertRaises(AssertionError):
            helpers.stage_erofs('odm', base, {relative: entry}, {relative: meta}, work, self.avb, self.avbtool)
        self.assertEqual(helpers.sha(base), baseline_hash)
        self.assertFalse((work / 'odm.img').exists())

    def test_erofs_alias_rejects_mismatched_baseline_target(self):
        base, fake_rom, relative, _, _, _, entry, meta = self.alias_fixture(mismatched=True)
        baseline_hash = helpers.sha(base)
        work = self.root / 'mismatched-alias-stage'
        work.mkdir()
        with patch.object(helpers, 'ROM', fake_rom), self.assertRaises(AssertionError):
            helpers.stage_erofs('odm', base, {relative: entry}, {relative: meta}, work, self.avb, self.avbtool)
        self.assertEqual(helpers.sha(base), baseline_hash)
        self.assertFalse((work / 'odm.img').exists())

    def test_packaging_inputs_are_frozen(self):
        fake_rom = self.root / 'rom'
        context = fake_rom / helpers.SEPOLICY_CONTEXTS
        context.parent.mkdir(parents=True)
        context.write_bytes(b'fixture contexts')
        info_relative = 'obj/PACKAGING/vendor_intermediates/vendor_image_info.txt'
        info = self.build / info_relative
        info.parent.mkdir(parents=True)
        info.write_bytes(b'vendor_fs_type=erofs\n')
        frozen = {'@sepolicy_file_contexts': helpers.sha(context), info_relative: helpers.sha(info)}
        with patch.object(helpers, 'ROM', fake_rom):
            helpers.validate_packaging_inputs({'vendor'}, frozen)
            for key in frozen:
                with self.assertRaises(AssertionError):
                    helpers.validate_packaging_inputs({'vendor'}, {k: v for k, v in frozen.items() if k != key})
            context.write_bytes(b'changed contexts')
            with self.assertRaises(AssertionError):
                helpers.validate_packaging_inputs({'vendor'}, frozen)
            with self.assertRaises(AssertionError):
                helpers.packaging_input_path('@unexpected')

    def test_two_descriptor_parent_merge_preserves_key_and_properties(self):
        old, new = {}, {}
        for name in ('odm', 'vendor'):
            for collection, content in ((old, b'old'), (new, b'new')):
                image = self.root / f'{name}-{content.decode()}.img'
                image.write_bytes(content * 65536)
                self.footer(image, name, 4 * 1024 * 1024)
                collection[name] = image
        parent = self.root / 'vbmeta-base.img'
        key = helpers.ROM / 'external/avb/test/data/testkey_rsa4096.pem'
        self.run_tool([helpers.HOST / 'avbtool', 'make_vbmeta_image', '--output', parent,
                       '--algorithm', 'SHA256_RSA4096', '--key', key,
                       '--rollback_index', '7', '--rollback_index_location', '2', '--flags', '2',
                       '--prop', 'preserved:parent', '--padding_size', '8192',
                       '--include_descriptors_from_image', old['odm'],
                       '--include_descriptors_from_image', old['vendor']])
        digest = helpers.sha(parent)
        replacements = [helpers.tree_descriptor(self.avb, self.avbtool, new[p], p)[3]
                        for p in ('odm', 'vendor')]
        output = self.root / 'vbmeta.img'
        helpers.merge_parent(self.avb, self.avbtool, parent, replacements, output, 'SHA256_RSA4096', self.root)
        self.assertEqual(helpers.sha(parent), digest)
        with self.assertRaises(AssertionError):
            helpers.merge_parent(self.avb, self.avbtool, parent, replacements, parent, 'SHA256_RSA4096', self.root)
        with self.assertRaises(AssertionError):
            helpers.merge_parent(self.avb, self.avbtool, parent, replacements * 2,
                                 self.root / 'duplicate.img', 'SHA256_RSA4096', self.root)

    def test_atomic_publication_and_no_overwrite(self):
        outputs = {}
        for partition in ('system', 'vbmeta_system'):
            source = self.root / f'{partition}-fixture.bin'
            source.write_bytes(partition.encode())
            outputs[partition] = source
        destination = self.root / 'published'
        helpers.publish_batch(destination, outputs, {'fixture': True})
        self.assertEqual(sorted(p.name for p in destination.iterdir()),
                         ['SHA256SUMS', 'build-result.json', 'system.img', 'vbmeta_system.img'])
        with self.assertRaises(AssertionError):
            helpers.publish_batch(destination, outputs, {'fixture': True})
        self.assertEqual((destination / 'system.img').read_bytes(), b'system')


if __name__ == '__main__':
    unittest.main(verbosity=2)
