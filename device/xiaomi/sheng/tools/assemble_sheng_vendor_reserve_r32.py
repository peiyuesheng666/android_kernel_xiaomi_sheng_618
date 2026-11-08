#!/usr/bin/env python3
"""Check normal Make property mapping, then stage the vendor reserve property only."""
import argparse
import json
from pathlib import Path
import subprocess

from package_sheng_model_followup import PRODUCT, ROM, sha

DEVICE = Path(__file__).resolve().parents[1]
DIAG = Path('/root/sheng-lineage/hardware-diagnostics')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__ and DEVICE == ROM / 'device/xiaomi/sheng'
    audit = json.loads(args.audit.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert len(audit['repositories']) == 22 and all(r['fetch']['returncode'] == 0 for r in audit['repositories'])
    assert args.work.parent.resolve(strict=True) == DIAG and not args.work.exists()
    args.work.mkdir()
    board = DEVICE / 'BoardConfig.mk'
    source = [line for line in board.read_text().splitlines()
              if line.startswith('BOARD_VENDORIMAGE_PARTITION_RESERVED_SIZE :=')]
    assert source == ['BOARD_VENDORIMAGE_PARTITION_RESERVED_SIZE := 33554432']
    makefile = ROM / 'build/make/core/Makefile'
    mapping = [line for line in makefile.read_text().splitlines()
               if line.startswith('$(if $(BOARD_$(_var)IMAGE_PARTITION_RESERVED_SIZE),')]
    assert len(mapping) == 1
    expected = args.work / 'normal-reserved-property.txt'
    fixture = args.work / 'property-mapping.mk'
    fixture.write_text(source[0] + '\n_var := VENDOR\ndefine scoped-property\n' + mapping[0] +
        '\nendef\n.PHONY: all\nall:\n\t$(call scoped-property,vendor,' + str(expected) + ')\n')
    result = subprocess.run(['make', '-f', str(fixture)], cwd=ROM, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert expected.read_text() == 'vendor_reserved_size=33554432\n'
    key = 'obj/PACKAGING/vendor_intermediates/vendor_image_info.txt'
    target = PRODUCT / key
    old_spec = json.loads((DEVICE / 'docs/batch-r32-final-inputs-20261108.json').read_text())
    before_sha = sha(target)
    assert before_sha == old_spec['build_inputs'][key]
    before = target.read_text().splitlines()
    assert 'vendor_reserved_size=33554432' not in before and 'vendor_disable_sparse=true' in before
    assert 'erofs_default_compressor=lz4hc,9' in before
    after = sorted([line for line in before if line != 'vendor_disable_sparse=true'] +
                   expected.read_text().splitlines())
    (args.work / 'vendor_image_info.before.txt').write_bytes(target.read_bytes())
    (args.work / 'vendor_image_info.candidate.txt').write_text('\n'.join(after) + '\n')
    target.write_bytes((args.work / 'vendor_image_info.candidate.txt').read_bytes())
    report = dict(vendor_reserve_configuration_checked=True, normal_make_property_mapping_passed=True,
        reserved_bytes=33554432, compressor='lz4hc,9',
        scoped_configuration_assembly_only=True, full_product_build_passed=False,
        normal_product_module_build_passed=False, device_operated=False,
        normal_make_mapping=mapping[0], property_before_sha256=before_sha,
        property_after_sha256=sha(target),
        inputs_sha256={str(p): sha(p) for p in [board, makefile, args.audit, Path(__file__), fixture]},
        make_stdout=result.stdout, make_stderr=result.stderr)
    (args.work / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
