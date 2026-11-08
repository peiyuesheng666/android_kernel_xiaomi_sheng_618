#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare a real enforcing-SELinux/request_firmware QEMU regression."""
from pathlib import Path
import re
import shutil
import subprocess
from build_sheng618_upstream import ACK, environment


def prepare(root, rd, out, mode):
    host = Path('/root/sheng-lineage/lineage-24.0/out/host/linux-x86/bin')
    mdp = root / 'mdp'
    subprocess.run(['gcc', '-I' + str(ACK / 'include'),
                    '-I' + str(ACK / 'security/selinux/include'), '-I' + str(out / 'include'),
                    str(ACK / 'scripts/selinux/mdp/mdp.c'), '-o', str(mdp)], check=True)
    policy = root / 'policy.conf'
    subprocess.run([str(mdp), str(policy), str(root / 'file_contexts')], check=True)
    original = re.sub(r'^policycap .*;\n', '', policy.read_text(), flags=re.M)
    # Firmware is deliberately denied. Every unrelated permission starts allowed.
    original = original.replace('allow base_t base_t:system *;',
                                'allow base_t base_t:system ~{ firmware_load };')
    original = original.replace('type base_t;', 'type base_t;\ntype denied_t;')
    original += ('\ngenfscon sysfs /module/sheng_firmware_probe/parameters/denied '
                 'user_u:object_r:denied_t\n')
    for name, text in [('policy-start', original),
                       ('policy-test', original.replace('~{ firmware_load }', '~{ firmware_load module_load }'))]:
        source = root / (name + '.conf')
        source.write_text(text)
        subprocess.run([str(host / 'checkpolicy'), '-c', '33', '-o', str(rd / name), str(source)],
                       check=True, stdout=subprocess.DEVNULL)
    probe = root / 'firmware-probe'
    probe.mkdir(exist_ok=True)
    (probe / 'Makefile').write_text('obj-m := sheng_firmware_probe.o\n')
    (probe / 'sheng_firmware_probe.c').write_text(r'''
#include <linux/module.h>
#include <linux/device.h>
#include <linux/firmware.h>
#include <linux/string.h>
static struct device *test_device;
static int last_result = -999, denied;
static const char payload[] = "SHENG-FW-TEST";
static int run_set(const char *value, const struct kernel_param *kp)
{
    const struct firmware *fw = NULL;
    int command, ret = kstrtoint(value, 0, &command);
    const char *name;
    if (ret) return ret;
    if (command < 1 || command > 3) return -EINVAL;
    name = command == 1 ? "sheng-direct.bin" :
           command == 2 ? "sheng-fallback.bin" : "sheng-missing.bin";
    ret = request_firmware(&fw, name, test_device);
    if (!ret && (fw->size != sizeof(payload)-1 ||
                 memcmp(fw->data, payload, sizeof(payload)-1))) ret = -EBADMSG;
    last_result = ret;
    pr_notice("SHENG_FIRMWARE_ACTUAL command=%d result=%d\n", command, ret);
    release_firmware(fw);
    return 0;
}
static const struct kernel_param_ops run_ops = { .set = run_set };
module_param_cb(run, &run_ops, NULL, 0200);
module_param(last_result, int, 0444);
module_param(denied, int, 0444);
static int __init probe_init(void)
{
    test_device = root_device_register("sheng-fw-probe");
    return PTR_ERR_OR_ZERO(test_device);
}
static void __exit probe_exit(void) { root_device_unregister(test_device); }
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
''')
    with (root / 'firmware-module-build.log').open('w') as stream:
        subprocess.run(['make', '-C', str(ACK), 'O=' + str(out), 'ARCH=arm64', 'LLVM=1',
                        'LLVM_IAS=1', 'M=' + str(probe), '-j8', 'modules'], env=environment(8),
                       stdout=stream, stderr=subprocess.STDOUT, check=True)
    shutil.copyfile(probe / 'sheng_firmware_probe.ko', rd / 'sheng_firmware_probe.ko')
    (rd / 'lib/firmware').mkdir(parents=True, exist_ok=True)
    (rd / 'lib/firmware/sheng-direct.bin').write_bytes(b'SHENG-FW-TEST')
    (root / 'test-firmware.h').write_text('#define FIRMWARE_LEGACY ' + str(int(mode == 'legacy')) + '\n' + r'''
static int fw_write(const char *path, const void *data, size_t count)
{
    int fd = open(path, O_WRONLY);
    if (fd < 0) return -1;
    ssize_t done = write(fd, data, count);
    close(fd);
    return done == (ssize_t)count ? 0 : -1;
}
static int fw_read_int(const char *path)
{
    char data[64] = {0};
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -999;
    ssize_t n = read(fd, data, sizeof(data)-1);
    close(fd);
    return n > 0 ? atoi(data) : -998;
}
static int fw_policy(const char *path)
{
    struct stat st;
    int fd = open(path, O_RDONLY);
    if (fd < 0 || fstat(fd, &st)) return 1;
    char *buf = malloc(st.st_size);
    if (!buf) return 2;
    if (read(fd, buf, st.st_size) != st.st_size) return 3;
    close(fd);
    int result = fw_write("/selinux/load", buf, st.st_size);
    free(buf);
    return result;
}
static int fw_serve(int command)
{
    char path[256];
    const char *name = command == 2 ? "sheng-fallback.bin" : "sheng-missing.bin";
    snprintf(path, sizeof(path), "/sys/class/firmware/%s/loading", name);
    for (int i=0; i<150; i++) {
        if (!access(path, F_OK)) {
            if (command == 3) return fw_write(path, "-1", 2) ? 1 : 0;
            if (fw_write(path, "1", 1)) return 2;
            char data_path[256];
            snprintf(data_path, sizeof(data_path), "/sys/class/firmware/%s/data", name);
            if (fw_write(data_path, "SHENG-FW-TEST", 13)) return 3;
            return fw_write(path, "0", 1) ? 4 : 0;
        }
        usleep(20000);
    }
    return FIRMWARE_LEGACY ? 5 : 0;
}
static int test_firmware(int log, int console)
{
    mkdir("/sys", 0755); mkdir("/proc", 0755); mkdir("/selinux", 0755);
    if (mount("sysfs", "/sys", "sysfs", 0, "") ||
        mount("proc", "/proc", "proc", 0, "") ||
        mount("selinuxfs", "/selinux", "selinuxfs", 0, "")) return 61;
    if (fw_policy("/policy-start") || fw_write("/selinux/enforce", "1", 1)) return 62;
    int fd = open("/sheng_firmware_probe.ko", O_RDONLY);
    if (fd < 0 || syscall(SYS_finit_module, fd, "", 0)) return 63;
    close(fd);
    if (fw_policy("/policy-test")) return 64;
    if (fw_read_int("/selinux/enforce") != 1) return 65;
    if (fw_write("/proc/sys/kernel/firmware_config/force_sysfs_fallback", "1", 1)) return 66;
    if (fw_write("/sys/class/firmware/timeout", "4", 1)) return 67;
    const int expected[] = {FIRMWARE_LEGACY ? 0 : -EACCES,
                            FIRMWARE_LEGACY ? 0 : -ENOENT, -ENOENT};
    for (int command=1; command<=3; command++) {
        pid_t child = -1;
        if (command > 1) {
            child = fork();
            if (child == 0) _exit(fw_serve(command));
            if (child < 0) return 68;
        }
        char text = '0' + command;
        if (fw_write("/sys/module/sheng_firmware_probe/parameters/run", &text, 1)) return 69;
        if (child > 0) {
            int status;
            if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status)) return 70;
        }
        int actual = fw_read_int("/sys/module/sheng_firmware_probe/parameters/last_result");
        dprintf(console, "SHENG_FIRMWARE_CASE command=%d result=%d expected=%d enforcing=1\n",
                command, actual, expected[command-1]);
        if (actual != expected[command-1]) return 71;
    }
    errno = 0;
    fd = open("/sys/module/sheng_firmware_probe/parameters/denied", O_RDONLY);
    if (fd >= 0 || errno != EACCES) return 72;
    fd = open("/sheng_firmware_probe.ko", O_RDONLY);
    if (fd < 0) return 73;
    errno = 0;
    int result = syscall(SYS_finit_module, fd, "", 0), saved = errno;
    close(fd);
    dprintf(console, "SHENG_FIRMWARE_GUARDS denied_file=EACCES module_load=%d errno=%d\n", result, saved);
    if (result != -1 || saved != EACCES) return 74;
    const char *marker = FIRMWARE_LEGACY ?
        "<5>SHENG_FIRMWARE_POLICY_PASS mode=legacy enforcing=1 file_and_module_denials_retained\n" :
        "<5>SHENG_FIRMWARE_POLICY_PASS mode=native enforcing=1 file_and_module_denials_retained\n";
    if (write(log, marker, strlen(marker)) != (ssize_t)strlen(marker)) return 75;
    return 0;
}
''')
