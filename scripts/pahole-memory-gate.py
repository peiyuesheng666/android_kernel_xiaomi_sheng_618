#!/usr/bin/env python3
import os,sys,time
from pathlib import Path
real=os.environ['SHENG_REAL_PAHOLE']
args=sys.argv[1:]
if '--btf_base' in args and os.environ.get('SHENG_MODULE_BTF_BASE'):
    base=Path(os.environ['SHENG_MODULE_BTF_BASE'])
    assert base.is_file()
    args[args.index('--btf_base')+1]=str(base)
if '-J' in args and '--btf_base' not in args:
    args=[('-j1' if value.startswith('-j') else value) for value in args]
    os.nice(10)
    announced=False
    while True:
        info=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
        if int(info['MemAvailable'].split()[0]) >= 3*1024*1024:
            break
        if not announced:
            print('Core BTF waiting for 3 GiB available RAM; pinned tool and type flags unchanged.',flush=True)
            announced=True
        time.sleep(5)
os.execv(real,[real,*args])
