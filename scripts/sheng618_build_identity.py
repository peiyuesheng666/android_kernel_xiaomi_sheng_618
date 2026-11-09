#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Apply the user's kernel build identity without changing compiler selection."""
import difflib
import hashlib
import json
import subprocess
from pathlib import Path
import sheng618_root_policy

LOCAL_SUFFIX = '-peiyuesheng-sheng-kernel'
BUILD_USER = 'peiyuesheng'
BUILD_HOST = 'MiFans'


def configure(ack, output, project):
    sheng618_root_policy.configure(ack, output, project)
    config = output / '.config'
    subprocess.run([ack / 'scripts/config', '--file', config,
                    '--set-str', 'LOCALVERSION', LOCAL_SUFFIX,
                    '--disable', 'LOCALVERSION_AUTO'], check=True)
    path = ack / 'scripts/mkcompile_h'
    before = path.read_text()
    anchor = 'cat <<EOF\n'
    short = '''# SHENG_SHORT_COMPILER: display the real tool versions, omitting repository URLs.
# CC_VERSION_TEXT and compiler detection remain unchanged in Kbuild/Kconfig.
case "$CC_VERSION" in
    *"clang version "*)
        CC_VERSION=$(printf '%s\\n' "$CC_VERSION" |
            sed -n 's/.*clang version \\([^ ]*\\).*/Clang \\1/p')
        ;;
esac
case "$LD_VERSION" in
    "LLD "*) LD_VERSION=$(printf '%s\\n' "$LD_VERSION" | awk '{print $1 " " $2}') ;;
esac

'''
    if short in before:
        before = before.replace(short, '', 1)
    assert 'SHENG_SHORT_COMPILER' not in before and before.count(anchor) == 1
    after = before.replace(anchor, short + anchor, 1)
    path.write_text(after)
    folder = project / 'device/xiaomi/sheng/interfaces/kernel/6.18'
    (folder / 'short-build-compiler.patch').write_text(''.join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True),
        fromfile='a/scripts/mkcompile_h', tofile='b/scripts/mkcompile_h')))
    report = dict(localversion=LOCAL_SUFFIX, localversion_auto=False,
                  localversion_environment='', build_user=BUILD_USER, build_host=BUILD_HOST,
                  source='scripts/mkcompile_h',
                  before_sha256=hashlib.sha256(before.encode()).hexdigest(),
                  after_sha256=hashlib.sha256(after.encode()).hexdigest(),
                  compiler_selection_changed=False,
                  full_compiler_provenance_preserved_in_build_report=True,
                  reference='Selected ACK ff4a6c3bb0f471a9dd186293a47b62c83829b97d scripts/mkcompile_h; user-requested display formatting')
    (project / 'reports/kernel618-build-identity-source.json').write_text(json.dumps(report, indent=2) + '\n')


def verify(output, expected_release):
    release = (output / 'include/config/kernel.release').read_text().strip()
    assert release == expected_release, release
    text = (output / 'include/generated/compile.h').read_text()
    assert f'"{BUILD_USER}"' in text and f'"{BUILD_HOST}"' in text, text
    assert 'https://' not in text and 'http://' not in text and 'googlesource' not in text, text
    return dict(release=release, compile_header=text,
                root_policy=sheng618_root_policy.verify(output, Path(__file__).resolve().parents[1]))
