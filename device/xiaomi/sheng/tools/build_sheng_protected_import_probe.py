#!/usr/bin/env python3
"""Build an offscreen EGL import diagnostic from pinned vendor compile commands."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROM = Path('/root/sheng-lineage/lineage-24.0')
DEVICE = Path(__file__).resolve().parents[1]
TEMPLATE = Path('/root/sheng-lineage/hardware-diagnostics/graphicbuffer-abi-r25/commands.json')
TEMPLATE_SHA = 'fd49731a606f47dd3028d1a7175c9acee8b096d56b44f267323ad281dc3ecc1a'
REQUIRED = {'frameworks/native', 'hardware/qcom-caf/sm8550/display', 'external/skia'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    args = parser.parse_args()
    assert __debug__ and DEVICE == ROM / 'device/xiaomi/sheng'
    audit = json.loads(args.audit.read_text())
    assert audit['known_public_sources_passed'] and not audit['all_project_nonclean_status']
    assert REQUIRED <= {r['path'] for r in audit['repositories']}
    assert all(r['passed'] and r['fetch']['returncode'] == 0 for r in audit['repositories'])
    assert sha(TEMPLATE) == TEMPLATE_SHA
    work = args.work
    assert work.is_absolute() and work.parent.resolve(strict=True) == TEMPLATE.parent.parent
    assert not work.exists()
    work.mkdir()
    compile_args, link_args = json.loads(TEMPLATE.read_text())
    compile_args[compile_args.index('-o') + 1] = str(work / 'probe.o')
    compile_args[compile_args.index('-MF') + 1] = str(work / 'probe.d')
    compile_args[-1] = str(DEVICE / 'tools/ShengProtectedImportProbe.cpp')
    compile_args[-1:-1] = ['-Iframeworks/native/opengl/include']
    response = [s for s in link_args if s.startswith('@')]
    assert len(response) == 1
    inputs = shlex.split(Path(response[0][1:]).read_text())
    inputs[0] = str(work / 'probe.o')
    egl = list((ROM / 'out/soong/.intermediates/frameworks/native/opengl/libs/libEGL').glob(
        'android_vendor_arm64*_shared/libEGL.so'))
    assert len(egl) == 1
    inputs.append(str(egl[0]))
    rsp = work / 'probe.rsp'
    rsp.write_text(shlex.join(inputs) + '\n')
    link_args[link_args.index(response[0])] = '@' + str(rsp)
    output = work / 'sheng-protected-import-probe'
    link_args[link_args.index('-o') + 1] = str(output)
    commands = []
    for command in (compile_args, link_args):
        result = subprocess.run(command, cwd=ROM, text=True, capture_output=True)
        commands.append(dict(command=command, returncode=result.returncode,
                             stdout=result.stdout, stderr=result.stderr))
        (work / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        assert result.returncode == 0, result.stderr
    report = dict(scoped_diagnostic_build_passed=True, full_product_build_passed=False,
        source_sha256=sha(DEVICE / 'tools/ShengProtectedImportProbe.cpp'),
        builder_sha256=sha(Path(__file__)), template_sha256=sha(TEMPLATE),
        audit_sha256=sha(args.audit), public_repositories=len(audit['repositories']),
        output=dict(path=str(output), sha256=sha(output), bytes=output.stat().st_size),
        camera_opened=False, pixels_read=False, installed_in_product=False,
        input_sha256={str(p): sha(p if p.is_absolute() else ROM / p)
                      for p in map(Path, inputs[1:])})
    (work / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
