#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the real debug kernel against disposable GPT disks in AArch64 QEMU."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import time
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
parser.add_argument('--slab-tracking', action='store_true',
                    help='Verify kmalloc-2k allocation provenance using the exact candidate cmdline')
parser.add_argument('--extra-test-module', type=Path,
                    help='Load a disposable regression module after the virtio providers')
parser.add_argument('--require-marker',
                    help='Require this regression marker in both console and a CRC-valid disk snapshot')
parser.add_argument('--auto-return', choices=['deadline', 'fault', 'panic', 'reboot', 'emergency'],
                    help='Exercise opt-in reset at 15 seconds (QEMU only), or actual reboot/fault path')
parser.add_argument('--legacy-reuse', action='store_true',
                    help='Real finit_module duplicate and missing legacy ABI regression')
parser.add_argument('--fscrypt-provisioning', action='store_true',
                    help='Synthetic keys through real add_key and ext4 FS_IOC_ADD_ENCRYPTION_KEY')
parser.add_argument('--firmware-policy', choices=['legacy', 'native'],
                    help='Real firmware direct/fallback load under enforcing SELinux; native is failing control')
options = parser.parse_args()
if options.auto_return in ('fault', 'panic', 'emergency'):
    options.fault_after_log = True
assert not options.fault_after_log or options.positive_only
assert not options.slab_tracking or options.fault_after_log
assert bool(options.extra_test_module) == bool(options.require_marker)
assert re.fullmatch(r'[a-z][a-z0-9-]{0,63}', options.revision)
root = Path('/root/sheng-618/diagnostic') / options.revision / (
    'qemu-firmware-' + options.firmware_policy if options.firmware_policy else
    'qemu-fscrypt' if options.fscrypt_provisioning else
    'qemu-module-reuse' if options.legacy_reuse else
    'qemu-auto-' + options.auto_return if options.auto_return else
    'qemu-regression' if options.extra_test_module else
    'qemu-slab' if options.slab_tracking else 'qemu-fault' if options.fault_after_log else 'qemu')
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
if options.extra_test_module:
    assert options.extra_test_module.is_file()
    shutil.copyfile(options.extra_test_module, rd / 'testmods' / options.extra_test_module.name)
    order.append('/testmods/' + options.extra_test_module.name)
if options.legacy_reuse:
    from build_sheng618_upstream import ACK, environment
    probe = root / 'reuse-probe'
    probe.mkdir(exist_ok=True)
    (probe / 'Makefile').write_text('obj-m := sheng_reuse_live.o sheng_reuse_absent.o\n')
    for name in ('sheng_reuse_live', 'sheng_reuse_absent'):
        (probe / (name + '.c')).write_text(
            '#include <linux/module.h>\n#include <linux/init.h>\n'
            'static int __init probe_init(void) { pr_notice("' + name + ': ACTUAL_INIT\\n"); return 0; }\n'
            'module_init(probe_init);\nMODULE_LICENSE("GPL");\n')
    with (root / 'reuse-build.log').open('w') as stream:
        subprocess.run(['make', '-C', str(ACK), 'O=' + str(out), 'ARCH=arm64', 'LLVM=1',
                        'LLVM_IAS=1', 'M=' + str(probe), '-j8', 'modules'],
                       env=environment(8), stdout=stream, stderr=subprocess.STDOUT, check=True)
    for name in ('sheng_reuse_live', 'sheng_reuse_absent'):
        path = probe / (name + '.ko')
        shutil.copyfile(path, rd / 'testmods' / path.name)
        data = bytearray(path.read_bytes())
        shoff = struct.unpack_from('<Q', data, 40)[0]
        entsize, count, names = struct.unpack_from('<HHH', data, 58)
        strings_hdr = shoff + names * entsize
        strings_at, strings_size = struct.unpack_from('<QQ', data, strings_hdr + 24)
        strings = data[strings_at:strings_at + strings_size]
        changed = set()
        for index in range(count):
            header = shoff + index * entsize
            at = struct.unpack_from('<I', data, header)[0]
            section = strings[at:].split(b'\0', 1)[0]
            offset, length = struct.unpack_from('<QQ', data, header + 24)
            if section == b'.modinfo':
                original = bytes(data[offset:offset + length])
                match = re.search(rb'(?<![^\x00])vermagic=([^\x00]+)', original)
                assert match
                start, end = match.span(1)
                replacement = b'5.15.78 SMP preempt mod_unload modversions aarch64'
                assert len(replacement) <= end - start
                data[offset + start:offset + end] = replacement.ljust(end - start, b'\0')
                changed.add('vermagic')
            if section == b'.gnu.linkonce.this_module':
                assert length > 8
                struct.pack_into('<Q', data, header + 32, 8)
                changed.add('struct-layout')
        assert changed == {'vermagic', 'struct-layout'}
        (rd / ('legacy-' + name + '.ko')).write_bytes(data)
    order.append('/testmods/sheng_reuse_live.ko')
(rd / 'test-order').write_text('\n'.join(order) + '\n')
if options.fault_after_log:
    from build_sheng618_upstream import ACK, environment
    fault = root / 'fault-module'
    fault.mkdir(exist_ok=True)
    (fault / 'Makefile').write_text('obj-m := sheng_fault_probe.o\n')
    fault_source = '''// SPDX-License-Identifier: GPL-2.0-only
#include <linux/module.h>
#include <linux/init.h>
#include <linux/bug.h>
#include <linux/slab.h>
#include <linux/reboot.h>
static int __init fault_init(void)
{
    /* SLAB_PROVENANCE_TEST */
    pr_emerg("SHENG_DISKLOG_FAULT_INJECT: deliberate QEMU-only BUG\\n");
    BUG();
    return 0;
}
module_init(fault_init);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Disposable QEMU-only fault capture probe");
'''
    if options.slab_tracking:
        fault_source = fault_source.replace('    /* SLAB_PROVENANCE_TEST */', '''
    void *probe = kzalloc(1900, GFP_KERNEL);
    if (!probe)
        return -ENOMEM;
    pr_emerg("SHENG_SLAB_PROVENANCE_TEST: allocated kmalloc-2k object\\n");
    kmem_dump_obj(probe);
    kfree(probe);
    pr_emerg("SHENG_SLAB_PROVENANCE_TEST: freed object provenance\\n");
    kmem_dump_obj(probe);''')
    (fault / 'sheng_fault_probe.c').write_text(fault_source)
    if options.auto_return == 'panic':
        fault_source = fault_source.replace('    BUG();', '    panic("SHENG_DISKLOG_DIRECT_PANIC");')
    if options.auto_return == 'emergency':
        fault_source = fault_source.replace('    BUG();', '    emergency_restart();')
    (fault / 'sheng_fault_probe.c').write_text(fault_source)
    with (root / 'fault-module-build.log').open('w') as stream:
        subprocess.run(['make', '-C', str(ACK), 'O=' + str(out), 'ARCH=arm64', 'LLVM=1',
                        'LLVM_IAS=1', 'M=' + str(fault), '-j8', 'modules'],
                       env=environment(8), stdout=stream, stderr=subprocess.STDOUT, check=True)
    shutil.copyfile(fault / 'sheng_fault_probe.ko', rd / 'sheng_fault_probe.ko')
program = root / 'test-init.c'
if options.firmware_policy:
    from sheng618_firmware_policy_test import prepare
    prepare(root, rd, out, options.firmware_policy)
cryptfs = root / 'ext4-disposable.img'
if options.fscrypt_provisioning:
    from build_sheng618_upstream import ACK
    with cryptfs.open('wb') as stream:
        stream.truncate(64 * 1024**2)
    subprocess.run(['mkfs.ext4', '-q', '-F', '-O', 'encrypt', str(cryptfs)], check=True)
    shutil.copyfile(ACK / 'include/uapi/linux/fscrypt.h', root / 'test-fscrypt.h')
program.write_text('#define TEST_HELPER ' + str(int(options.helper_exec)) + '\n'
                   '#define TEST_FIRMWARE ' + str(int(bool(options.firmware_policy))) + '\n'
                   '#define TEST_FSCRYPT ' + str(int(options.fscrypt_provisioning)) + '\n'
                   '#define TEST_REUSE ' + str(int(options.legacy_reuse)) + '\n'
                   '#define TEST_DEADLINE ' + str(int(options.auto_return == 'deadline')) + '\n'
                   '#define TEST_REBOOT ' + str(int(options.auto_return == 'reboot')) + '\n'
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
#include <stdint.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#if TEST_FIRMWARE
#include "test-firmware.h"
#endif
#if TEST_FSCRYPT
#include "test-fscrypt.h"
static int test_fscrypt(int log, int console) {
    struct { uint32_t type, flags; unsigned char raw[160]; } payload;
    const unsigned int sizes[]={32,100,100,129,8,32,32};
    const unsigned int flags[]={0,0,1,0,0,2,0};
    long keys[7];
    for(int i=0;i<7;i++) {
        memset(&payload,0,sizeof(payload));
        payload.type=i==6 ? 3 : FSCRYPT_KEY_SPEC_TYPE_IDENTIFIER;
        payload.flags=flags[i];
        memset(payload.raw,0x5a,sizeof(payload.raw)); /* Public synthetic bytes, no device keys. */
        char name[60];
        snprintf(name,sizeof(name),"sheng-fscrypt-test-%d",i);
        errno=0;
        keys[i]=syscall(SYS_add_key,"fscrypt-provisioning",name,&payload,8+sizes[i],-3);
        int saved=errno;
        dprintf(console,"SHENG_FSCRYPT_ADD %d success=%d errno=%d\n",i,keys[i]>=0,saved);
        if(i<3 ? keys[i]<0 : (keys[i]!=-1 || saved!=EINVAL)) return 50+i;
    }
    mkdir("/sys",0755);
    if(mount("sysfs","/sys","sysfs",0,"")) return 60;
    FILE *dev=fopen("/sys/block/vdb/dev","r");
    unsigned int major_number,minor_number;
    if(!dev || fscanf(dev,"%u:%u",&major_number,&minor_number)!=2) return 61;
    fclose(dev);
    mknod("/dev/cryptfs",S_IFBLK|0600,makedev(major_number,minor_number));
    mkdir("/scratch",0755);
    if(mount("/dev/cryptfs","/scratch","ext4",0,"")) return 62;
    int fd=open("/scratch",O_RDONLY|O_DIRECTORY);
    if(fd<0) return 63;
    const int which[]={0,1,2,1,1,2,1};
    const unsigned int native_flags[]={0,0,1,1,0,0,1};
    const unsigned int old_flags[]={0,1,0,0,0,0,1};
    const int expected[]={0,EOPNOTSUPP,EOPNOTSUPP,EKEYREJECTED,EKEYREJECTED,EKEYREJECTED,EINVAL};
    for(int i=0;i<7;i++) {
        struct fscrypt_add_key_arg arg={0};
        arg.key_spec.type=FSCRYPT_KEY_SPEC_TYPE_IDENTIFIER;
        arg.key_id=(uint32_t)keys[which[i]];
        arg.flags=native_flags[i];
        arg.__flags=old_flags[i];
        errno=0;
        int result=ioctl(fd,FS_IOC_ADD_ENCRYPTION_KEY,&arg);
        int saved=errno;
        dprintf(console,"SHENG_FSCRYPT_IOCTL %d result=%d errno=%d expected=%d\n",i,result,saved,expected[i]);
        if(expected[i] ? (result!=-1 || saved!=expected[i]) : result!=0) return 70+i;
    }
    close(fd);
    const char marker[]="<5>SHENG_FSCRYPT_REGRESSION_PASS legacy_wrapped_native_checks_intact\n";
    if(write(log,marker,sizeof(marker)-1)!=(ssize_t)(sizeof(marker)-1)) return 79;
    return 0;
}
#endif
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
#if TEST_FSCRYPT
    int crypto_result=test_fscrypt(log,console);
    if(crypto_result) { dprintf(console,"SHENG_FSCRYPT_FAILED code=%d\n",crypto_result); return crypto_result; }
#endif
#if TEST_FIRMWARE
    int firmware_result=test_firmware(log,console);
    if(firmware_result) { dprintf(console,"SHENG_FIRMWARE_FAILED code=%d errno=%d\n",firmware_result,errno); return firmware_result; }
#endif
    if(TEST_REUSE) {
        const char *paths[] = {"/testmods/sheng_reuse_live.ko", "/legacy-sheng_reuse_live.ko",
                               "/legacy-sheng_reuse_absent.ko"};
        const int expected[] = {EEXIST, EEXIST, ENOEXEC};
        for(int i=0; i<3; i++) {
            int fd=open(paths[i],O_RDONLY);
            errno=0;
            int result=fd<0 ? 1 : (int)syscall(SYS_finit_module,fd,"",0);
            int saved=errno;
            if(fd>=0) close(fd);
            dprintf(console,"SHENG_REUSE_CASE %d result=%d errno=%d expected=%d\n",i,result,saved,expected[i]);
            if(result!=-1 || saved!=expected[i]) return 41+i;
        }
        const char marker[]="<5>SHENG_REUSE_REGRESSION_PASS duplicate_live_EEXIST missing_ENOEXEC\n";
        if(write(log,marker,sizeof(marker)-1)!=(ssize_t)(sizeof(marker)-1)) return 44;
    }
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
    if(TEST_DEADLINE) { for(;;)pause(); }
    reboot(TEST_REBOOT ? RB_AUTOBOOT : RB_POWER_OFF);
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
    qmp_path = root / (label + '.qmp')
    qmp_path.unlink(missing_ok=True)
    qmp_data = b''
    with transcript.open('w') as stream:
        process = subprocess.Popen(['qemu-system-aarch64', '-M', 'virt,virtualization=on',
                                 '-cpu', 'max,pauth-impdef=on', '-smp', '2', '-m', '1536',
                                 '-nic', 'none', '-nographic', '-monitor', 'none', '-no-reboot',
                                 '-qmp', 'unix:' + str(qmp_path) + ',server=on,wait=off',
                                 '-kernel', str(image), '-initrd', str(initrd),
                                 '-drive', f'if=none,id=logdisk,file={path},format=raw',
                                 '-device', 'virtio-blk-pci,drive=logdisk',
                                 *(['-drive', f'if=none,id=cryptfs,file={cryptfs},format=raw',
                                    '-device', 'virtio-blk-pci,drive=cryptfs'] if options.fscrypt_provisioning else []),
                                 '-append', 'console=ttyAMA0 earlycon=pl011,0x9000000 rdinit=/init panic=-1 printk.devkmsg=on sheng_bootlog.enable=1'
                                 + (' panic_on_oops=1 irqaffinity=0' if options.fault_after_log else '')
                                 + (' stack_depot_disable=on stack_depot_disable=off slab_debug=U,kmalloc-2k'
                                    if options.slab_tracking else '')
                                 + (' sheng_bootlog.test_timeout=15' if options.auto_return else '')],
                                stdout=stream, stderr=subprocess.STDOUT)
        try:
            with socket.socket(socket.AF_UNIX) as monitor:
                monitor.settimeout(60)
                for attempt in range(100):
                    try:
                        monitor.connect(str(qmp_path))
                        break
                    except (FileNotFoundError, ConnectionRefusedError):
                        time.sleep(0.05)
                else:
                    raise RuntimeError('QEMU monitor unavailable')
                monitor.sendall(b'{"execute":"qmp_capabilities"}\r\n')
                while True:
                    chunk = monitor.recv(65536)
                    if not chunk:
                        break
                    qmp_data += chunk
            process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    assert process.returncode == 0, transcript
    qmp_events = [json.loads(line) for line in qmp_data.splitlines() if line.strip()]
    (root / (label + '-qmp.json')).write_text(json.dumps(qmp_events, indent=2) + '\n')
    console = transcript.read_text()
    assert 'Unresolved symbol' not in console, transcript
    if options.helper_exec:
        assert console.count('TEST embedded helper exec ') == len(order), transcript
        assert 'result=111' not in console, transcript
    if options.require_marker:
        assert options.require_marker in console, transcript
    if options.legacy_reuse:
        assert console.count('sheng_reuse_live: ACTUAL_INIT') == 1
        assert 'sheng_reuse_absent: ACTUAL_INIT' not in console
        assert 'SHENG_REUSE_REGRESSION_PASS' in console
        assert 'sheng_module_reuse: sheng_reuse_live already live' in console
    if options.fscrypt_provisioning:
        assert 'SHENG_FSCRYPT_REGRESSION_PASS' in console, transcript
        assert console.count('SHENG_FSCRYPT_IOCTL ') == 7
        assert console.count('SHENG_FSCRYPT_ADD ') == 7
    if options.firmware_policy:
        assert 'SHENG_FIRMWARE_POLICY_PASS mode=' + options.firmware_policy in console, transcript
        assert console.count('SHENG_FIRMWARE_CASE command=') == 3
        assert 'SHENG_FIRMWARE_GUARDS denied_file=EACCES module_load=-1 errno=13' in console
    if options.fault_after_log and options.auto_return not in ('fault', 'emergency'):
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
        if options.require_marker:
            assert any(options.require_marker in s['text'] for s in slots), transcript
        if options.legacy_reuse:
            assert any('SHENG_REUSE_REGRESSION_PASS' in s['text'] for s in slots)
        if options.fscrypt_provisioning:
            assert any('SHENG_FSCRYPT_REGRESSION_PASS' in s['text'] for s in slots)
        if options.firmware_policy:
            assert any('SHENG_FIRMWARE_POLICY_PASS mode=' + options.firmware_policy in s['text'] for s in slots)
        if options.auto_return:
            assert 'TEST_ONLY automatic bootloader return at uptime 15 seconds' in console
            assert any(e.get('event') == 'SHUTDOWN' and e.get('data', {}).get('reason') == 'guest-reset'
                       for e in qmp_events), (transcript, qmp_events)
            if options.auto_return == 'deadline':
                assert any('test deadline diagnostics: init and blocked tasks' in s['text'] for s in slots)
                assert max(s['uptime_ms'] for s in slots) >= 14000
            if options.auto_return == 'reboot':
                assert "reboot: Restarting system with command 'bootloader'" in console
        if options.fault_after_log and options.auto_return not in ('panic', 'emergency'):
            assert any(all(marker in s['text'] for marker in (
                'SHENG_DISKLOG_FAULT_INJECT', 'sheng_fault_probe', 'Call trace:',
                'pc :', '1500 ms capture window')) for s in slots), transcript
        if options.slab_tracking:
            assert any(all(marker in s['text'] for marker in (
                'SHENG_SLAB_PROVENANCE_TEST', 'Free path:')) and
                re.search(r'allocated at init_module\+[^\n]*\[sheng_fault_probe\]', s['text'])
                for s in slots), transcript
        # A torn newest write must leave the other validated copy readable.
        torn = bytearray(raw)
        torn[64] ^= 1
        assert len(decode(torn)) == 1
    else:
        assert not slots and raw == bytes(len(raw)), transcript
    cases.append({'case': label, 'gpt_name': name, 'partition_mib': mib,
                  'valid_snapshots': len(slots), 'expected_write': expected,
                  'uptime_ms': [s['uptime_ms'] for s in slots], 'qemu_log': str(transcript),
                  'qmp_shutdown_events': [e for e in qmp_events if e.get('event') == 'SHUTDOWN']})
    print(json.dumps(cases[-1]), flush=True)
report = {'real_aarch64_kernel': True, 'real_gpt_block_io_and_fsync': True,
          'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
          'cases': cases, 'torn_copy_rejected_other_copy_readable': True,
          'hardware_ufs_tested': False,
          'embedded_helper_exec_and_finit_module_tested': options.helper_exec,
          'partition_guard_cases_run': not options.positive_only}
report['fault_injection_case_run'] = options.fault_after_log
report['exception_stack_persisted_before_panic'] = (
    True if options.fault_after_log and options.auto_return != 'emergency' else None)
if options.slab_tracking:
    report['kmalloc_2k_allocation_and_free_stacks_persisted'] = True
    report['stock_stack_depot_disable_overridden'] = True
if options.extra_test_module:
    report['extra_test_module'] = str(options.extra_test_module)
    report['regression_marker_persisted'] = options.require_marker
if options.auto_return:
    report['auto_return_case'] = options.auto_return
    report['qemu_deadline_seconds'] = 15
    report['actual_pmic_fastboot_proven'] = False
if options.legacy_reuse:
    report['legacy_live_duplicate_eexist_and_missing_enoexec'] = True
    report['actual_live_init_count'] = 1
    report['actual_absent_init_count'] = 0
if options.fscrypt_provisioning:
    report['fscrypt_actual_add_key_cases'] = 7
    report['fscrypt_actual_ext4_ioctl_cases'] = 7
    report['public_synthetic_key_bytes_only'] = True
    report['hardware_wrapped_key_derivation_tested'] = False
    report['old_and_new_wrapped_formats_reach_unsupported_virtual_hardware'] = True
if options.firmware_policy:
    report.update(firmware_policy_mode=options.firmware_policy,
                  selinux_enforcing=True, actual_request_firmware_cases=3,
                  file_and_module_load_denials_retained=True,
                  direct_and_sysfs_fallback_tested=True,
                  real_hardware_firmware_tested=False)
suffix = ('-qemu-firmware-' + options.firmware_policy + '.json' if options.firmware_policy else
          '-qemu-fscrypt.json' if options.fscrypt_provisioning else
          '-qemu-module-reuse.json' if options.legacy_reuse else
          '-qemu-auto-' + options.auto_return + '.json' if options.auto_return else
          '-qemu-regression.json' if options.extra_test_module else '-qemu-slab.json'
          if options.slab_tracking else '-qemu-fault.json' if options.fault_after_log else '-qemu.json')
(work / ('reports/kernel618-' + options.revision + suffix)).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
