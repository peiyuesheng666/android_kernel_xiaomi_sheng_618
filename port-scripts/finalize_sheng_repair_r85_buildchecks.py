#!/usr/bin/env python3
"""Require final module BTF evidence in the full r85 verifier and export notes."""
from pathlib import Path
import shutil

workspace=Path(__file__).resolve().parents[1]
project=Path('/root/sheng-618-repair-r85-project')
path=project/'scripts/verify.py';text=path.read_text()
anchor="    result.update(fresh_build_verified=True, build=build, module_abi=json.loads(abi))"
assert text.count(anchor)==1
if "module-btf-final.json" not in text:
    extra='''
    btf = json.loads((k / 'out-gki/module-btf-final.json').read_text())
    assert btf['all_modules_passed'] and btf['module_count'] == 344
    for record in btf['modules']:
        with (k / 'out-gki/layer/lib/modules' / record['module']).open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == record['sha256']
        assert set(record['btf']) == {'.BTF', '.BTF.base'}
    result['module_btf'] = {key: value for key, value in btf.items() if key != 'modules'}
    result['source_model'] = 'pinned baseline cache plus inherited and repair-r85 patches'
'''
    text=text.replace(anchor,anchor+extra);path.write_text(text)
shutil.copyfile(workspace/'reports/kernel618-features-repair-r85.md',project/'docs/FEATURES-REPAIR-r85.zh-CN.md')
for name in ('finalize_sheng_repair_r85_buildchecks.py','flash_sheng_repair_r85_wireless.py',
             'check_sheng_repair_r85_nodes.py','probe_sheng_bypass_r85.py','verify_sheng_repair_r85_btf.py',
             'package_sheng_repair_r85.py','capture_sheng_pen_r85.py','analyze_sheng_pen_r85.py',
             'probe_sheng_standard_pps_r85.py'):
    shutil.copyfile(workspace/'scripts'/name,project/'port-scripts'/name)
print('Final BTF evidence required by verifier; feature notes and acceptance scripts preserved',flush=True)
