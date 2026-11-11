from pathlib import Path
import json
import shutil
w=Path(__file__).resolve().parents[1]
p=Path('/root/sheng-618-repair-r87-project')
path=p/'provenance/repair-r85.json';r=json.loads(path.read_text())
assert r['revision']=='repair-r87'
r.update(project=str(p),build='/root/sheng-618-repair-r86-build',reused_mutable_build_cache=True)
path.write_text(json.dumps(r,indent=2)+'\n')
(w/'reports/kernel618-repair-r87-stage.json').write_text(json.dumps(r,indent=2)+'\n')
path=p/'scripts/verify.py';s=path.read_text().replace("'repair_r86': repair_fix", "'repair_r87': repair_fix")
s=s.replace('combined repair-r86 patches','combined repair-r87 patches');path.write_text(s)
for name in ['prepare_sheng_repair_r87.py','fix_sheng_r87_provenance.py']:
    shutil.copyfile(w/'scripts'/name,p/'port-scripts'/name)
print('r87 project/build provenance and verifier revision labels corrected')
