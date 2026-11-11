#!/usr/bin/env python3
"""Check distilled module BTF against the final embedded r85 kernel."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess

workspace=Path(__file__).resolve().parents[1]
output=Path('/root/sheng-618-repair-r86-build/k618/out-gki')
tool=Path('/root/sheng-618-repair-r86-build/host-tools/btf-distill/sheng-btf-distill')
def btf(path):
    with path.open('rb') as f:
        header=f.read(64);assert header[:6]==b'\x7fELF\x02\x01'
        offset=struct.unpack_from('<Q',header,40)[0]
        size,count,strings=struct.unpack_from('<HHH',header,58)
        assert size==64
        f.seek(offset);rows=[struct.unpack('<IIQQQQIIQQ',f.read(size)) for _ in range(count)]
        f.seek(rows[strings][4]);names=f.read(rows[strings][5])
        for row in rows:
            if names[row[0]:].split(b'\0',1)[0]==b'.BTF':
                f.seek(row[4]);data=f.read(row[5]);assert data[:2]==b'\x9f\xeb';return data
    raise RuntimeError('BTF missing: '+str(path))
base=(output/'kernel-module-base.btf').read_bytes();final=btf(output/'vmlinux')
raw=output/'kernel-final-r85.btf';raw.write_bytes(final)
modules=sorted((output/'layer/lib/modules').glob('*.ko'));assert len(modules)==344
records=[]
for module in modules:
    result=subprocess.run([str(tool),'verify',str(raw),str(module)],capture_output=True,text=True)
    assert result.returncode==0,(module.name,result.stderr)
    records.append(dict(module=module.name,types=json.loads(result.stdout)))
report=dict(module_count=len(records),all_modules_parsed_against_final_kernel=True,
    kernel_btf_unchanged_from_module_build_base=base==final,
    distilled_modules_verified=True,kernel_btf_sha256=hashlib.sha256(final).hexdigest(),
    host_tool_sha256=hashlib.file_digest(tool.open('rb'),'sha256').hexdigest(),modules=records)
(workspace/'reports/kernel618-repair-r86-btf.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='modules'}),flush=True)
