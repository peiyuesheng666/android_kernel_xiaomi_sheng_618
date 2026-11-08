#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the real debug kernel against disposable GPT disks in AArch64 QEMU."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import uuid
import zlib

from read_sheng618_disklog import decode

work = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', default='disklog-r5')
parser.add_argument('--helper-exec', action='store_true')
parser.add_argument('--positive-only', action='store_true')
parser.add_argument('--fault-after-log', action='store_true',
                    help='On CPU 1, BUG in a disposable module and require its stack in disk snapshots')
options = parser.parse_args()
assert not options.fault_after_log or options.positive_only
assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}', options.revision)
root = Path('/root/sheng-618/diagnostic') / options.revision / ('qemu-fault' if options.fault_after_log else 'qemu')
root.mkdir(parents=True, exist_ok=True)
out = Path('/root/sheng-618/upstream-build/k618/out-gki')
image = work / 'artifacts' / ('sheng-6.18-' + options.revision) / 'Image'
assert image.is_file(), 'Build the disk logger Image first'
rd = root / 'rd'
(rd / 'testmods').mkdir(parents=True, exist_ok=True)
modules = {p.stem.replace('-', '_'): p for p in out.rglob('*.ko')}
order, done = [], set()


def include(name):
    name = name.replace('-', '_')
    if name in done:
        return
    done.add(name)
    path = modules[name]
    dep = subprocess.run(['/sbin/modinfo', '-F', 'depends', str(path)], check=True,
                         capture_output=True, text=True).stdout.strip()
    for item in dep.split(','):
        if item:
            include(item)
    shutil.copyfile(path, rd / 'testmods' / path.name)
    order.append('/testmods/' + path.name)


# This GKI build's modinfo dependency list omits the PCI helper providers.
# Load the real helper modules first; an unresolved-symbol boot is not a test
# of the logger's block I/O path.
for name in ('virtio_pci_modern_dev', 'virtio_pci_legacy_dev', 'virtio_pci', 'virtio_blk'):
    if name in modules:
        include(name)
assert any('virtio_blk' in p for p in order)
(rd / 'test-order').write_text('\n'.join(order) + '\n')
if options.fault_after_log:
    from build_sheng618_upstream import ACK, environment
    fault = root / 'fault-module'
    fault.mkdir(exist_ok=True)
    (fault / 'Makefile').write_text('obj-m := sheng_fault_probe.o\n')
    (fault / 'sheng_fault_probe.c').write_text('''// SPDX-License-Identifier: GPL-2.0-only
#include <linux/module.h>
#include <linux/init.h>
#include <linux/bug.h>
static int __init fault_init(void)
{
    pr_emerg("SHENG_DISKLOG_FAULT_INJECT: deliberate QEMU-only BUG\\n");
    BUG();
    return 0;
}
module_init(fault_init);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Disposable QEMU-only fault capture probe");
''')
    with (root / 'fault-module-build.log').open('w') as stream:
        subprocess.run(['make', '-C', str(ACK), 'O=' + str(out), 'ARCH=arm64', 'LLVM=1',
                        'LLVM_IAS=1', 'M=' + str(fault), '-j8', 'modules'],
                       env=environment(8), stdout=stream, stderr=subprocess.STDOUT, check=True)
    shutil.copyfile(fault / 'sheng_fault_probe.ko', rd / 'sheng_fault_probe.ko')
program = root / 'test-init.c'
program.write_text('#define TEST_HELPER ' + str(int(options.helper_exec)) + '\n'
                   '#define TEST_FAULT ' + str(int(options.fault_after_log)) + '\n' + r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/syscall.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <string.h>
#include <errno.h>
#include <sched.h>
int main(void) {
    if (getpid()!=1) return 20;
    mkdir("/dev",0755);
    mount("tmpfs","/dev","tmpfs",0,"");
    mknod("/dev/kmsg", S_IFCHR|0600,makedev(1,11));
    int log=open("/dev/kmsg",O_WRONLY);
    mknod("/dev/console",S_IFCHR|0600,makedev(5,1));
    int console=open("/dev/console",O_WRONLY);
    dprintf(console,"TEST kmsg fd=%d errno=%d\n",log,errno);
    FILE *f=fopen("/test-order","r");
    char path[512];
    while(f && fgets(path,sizeof(path),f)) {
        path[strcspn(path,"\r\n")]=0;
        int r;
        if(TEST_HELPER) {
            pid_t child=fork();
            if(child==0) {
                execl("/k618_umh","/k618_umh",path,"",(char *)NULL);
                _exit(111);
            }
            int status=0;
            if(child<0 || waitpid(child,&status,0)!=child || !WIFEXITED(status))
                return 22;
            r=WEXITSTATUS(status);
            dprintf(console,"TEST embedded helper exec %s result=%d\n",path,r);
        } else {
            int fd=open(path,O_RDONLY);
            r=fd<0?-1:(int)syscall(SYS_finit_module,fd,"",0);
            if(fd>=0)close(fd);
        }
        if(r) return 23;
    }
    if(f)fclose(f);
    for(int i=0;i<80;i++) {
        char record[100];
        int n=snprintf(record,sizeof(record),"<5>SHENG_DISKLOG_QEMU_ACTUAL record=%d\n",i);
        ssize_t written=write(log,record,n);
        if(written!=n) {
            dprintf(console,"TEST kmsg write=%zd errno=%d\n",written,errno);
            return 21;
        }
        usleep(100000);
    }
    if(TEST_FAULT) {
        sleep(3);
        pid_t child=fork();
        if(child==0) {
            cpu_set_t cpus;
            CPU_ZERO(&cpus);
            CPU_SET(1,&cpus);
            if(sched_setaffinity(0,sizeof(cpus),&cpus)) _exit(31);
            int fd=open("/sheng_fault_probe.ko",O_RDONLY);
            if(fd<0) _exit(32);
            syscall(SYS_finit_module,fd,"",0);
            _exit(33);
        }
        int status=0;
        if(child<0 || waitpid(child,&status,0)!=child) return 34;
        dprintf(console,"FAULT TEST unexpectedly survived status=%d\n",status);
        return 35;
    }
    sleep(1);
    reboot(RB_POWER_OFF);
    for(;;)pause();
}
''')
subprocess.run(['aarch64-linux-gnu-gcc', '-static', '-O2', '-Wall', '-Wextra', '-Werror',
                str(program), '-o', str(rd / 'init')], check=True)
cpio = subprocess.run(['/root/sheng-lineage/lineage-24.0/out/host/linux-x86/bin/mkbootfs', str(rd)],
                      check=True, capture_output=True).stdout
initrd = root / 'initramfs.cpio'
initrd.write_bytes(cpio)


def disk(path, name, mib):
    sectors = 304 * 1024**2 // 512
    entries = bytearray(128 * 128)
    entries[:16] = uuid.UUID('0fc63daf-8483-4772-8e79-3d69d8477de4').bytes_le
    entries[16:32] = uuid.uuid4().bytes_le
    struct.pack_into('<QQQ', entries, 32, 2048, 2048 + mib * 2048 - 1, 0)
    label = name.encode('utf-16le')
    entries[56:56 + len(label)] = label
    disk_guid = uuid.uuid4().bytes_le

    def header(at, other, table):
        raw = bytearray(struct.pack('<8sIIIIQQQQ16sQIII', b'EFI PART', 0x10000, 92, 0, 0,
                                    at, other, 34, sectors - 34, disk_guid, table, 128, 128,
                                    zlib.crc32(entries)))
        struct.pack_into('<I', raw, 16, zlib.crc32(raw))
        return raw

    with path.open('wb') as stream:
        stream.truncate(sectors * 512)
        mbr = bytearray(512)
        mbr[450] = 0xee
        struct.pack_into('<II', mbr, 454, 1, sectors - 1)
        mbr[510:512] = b'\x55\xaa'
        stream.write(mbr)
        stream.write(header(1, sectors - 1, 2))
        stream.seek(2 * 512)
        stream.write(entries)
        stream.seek((sectors - 33) * 512)
        stream.write(entries)
        stream.seek((sectors - 1) * 512)
        stream.write(header(sectors - 1, 1, sectors - 33))


cases = []
inputs = [('valid', 'rawdump', 300, True)]
if not options.positive_only:
    inputs += [('wrong-name', 'not-rawdump', 300, False), ('wrong-size', 'rawdump', 299, False)]
for label, name, mib, expected in inputs:
    path = root / (label + '.img')
    disk(path, name, mib)
    transcript = root / (label + '.log')
    with transcript.open('w') as stream:
        result = subprocess.run(['qemu-system-aarch64', '-M', 'virt,virtualization=on',
                                 '-cpu', 'max,pauth-impdef=on', '-smp', '2', '-m', '1536',
                                 '-nic', 'none', '-nographic', '-monitor', 'none', '-no-reboot',
                                 '-kernel', str(image), '-initrd', str(initrd),
                                 '-drive', f'if=none,id=logdisk,file={path},format=raw',
                                 '-device', 'virtio-blk-pci,drive=logdisk',
                                 '-append', 'console=ttyAMA0 earlycon=pl011,0x9000000 rdinit=/init panic=-1 printk.devkmsg=on sheng_bootlog.enable=1'
                                 + (' panic_on_oops=1 irqaffinity=0' if options.fault_after_log else '')],
                                stdout=stream, stderr=subprocess.STDOUT, timeout=60)
    assert result.returncode == 0, transcript
    console = transcript.read_text()
    assert 'Unresolved symbol' not in console, transcript
    if options.helper_exec:
        assert console.count('TEST embedded helper exec ') == len(order), transcript
        assert 'result=111' not in console, transcript
    if options.fault_after_log:
        assert 'Kernel panic - not syncing:' in console, transcript
        assert 'FAULT TEST unexpectedly survived' not in console, transcript
    with path.open('rb') as stream:
        stream.seek((1 + 288) * 1024**2)
        raw = stream.read(2 * 1024**2)
    slots = decode(raw)
    if expected:
        assert len(slots) == 2, transcript
        assert all('SHENG_DISKLOG_QEMU_ACTUAL' in s['text'] for s in slots)
        assert max(s['uptime_ms'] for s in slots) >= 5000
        if options.fault_after_log:
            assert any(all(marker in s['text'] for marker in (
                'SHENG_DISKLOG_FAULT_INJECT', 'sheng_fault_probe', 'Call trace:',
                'pc :', '1500 ms capture window')) for s in slots), transcript
        # A torn newest write must leave the other validated copy readable.
        torn = bytearray(raw)
        torn[64] ^= 1
        assert len(decode(torn)) == 1
    else:
        assert not slots and raw == bytes(len(raw)), transcript
    cases.append({'case': label, 'gpt_name': name, 'partition_mib': mib,
                  'valid_snapshots': len(slots), 'expected_write': expected,
                  'uptime_ms': [s['uptime_ms'] for s in slots], 'qemu_log': str(transcript)})
    print(json.dumps(cases[-1]), flush=True)
report = {'real_aarch64_kernel': True, 'real_gpt_block_io_and_fsync': True,
          'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
          'cases': cases, 'torn_copy_rejected_other_copy_readable': True,
          'hardware_ufs_tested': False,
          'embedded_helper_exec_and_finit_module_tested': options.helper_exec,
          'partition_guard_cases_run': not options.positive_only}
report['fault_injection_case_run'] = options.fault_after_log
report['exception_stack_persisted_before_panic'] = True if options.fault_after_log else None
suffix = '-qemu-fault.json' if options.fault_after_log else '-qemu.json'
(work / ('reports/kernel618-' + options.revision + suffix)).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
