// SPDX-License-Identifier: Apache-2.0
// Diagnostic-only PID 1. No partition writes, forced modules, or remote shell.
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/vfs.h>
#include <sys/syscall.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#ifndef SHENG_DIAG_INIT
#define SHENG_DIAG_INIT "/system/bin/init"
#endif
#ifndef SHENG_DIAG_SERIAL
#define SHENG_DIAG_SERIAL "SHENG-DIAG-R3"
#endif

#define GADGET "/config/usb_gadget/sheng_diag"
#define CACHE_SIZE (8 * 1024 * 1024)
static int kernel_log = -1;
static int report_reader = -1;
static int report_writer = -1;
static bool gadget_bound;
static bool peripheral_mode_set;

static void report(const char *format, ...) {
    char data[2048];
    va_list ap;
    va_start(ap, format);
    int len = vsnprintf(data, sizeof(data), format, ap);
    va_end(ap);
    if (len < 0) return;
    char record[2304];
    int count = snprintf(record, sizeof(record), "[sheng-diag-r7] %s\n", data);
    if (report_writer >= 0 && count > 0) {
        ssize_t written = write(report_writer, record, (size_t)count);
        (void)written;
    }
    if (kernel_log >= 0) {
        if (dprintf(kernel_log, "<6>sheng-diag-r4: %.900s\n", data) < 0) { }
    } else {
        if (dprintf(STDERR_FILENO, "sheng-diag-r3: %s\n", data) < 0) { }
    }
}

static bool read_text(const char *path, char *data, size_t size) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return false;
    ssize_t len = read(fd, data, size - 1);
    close(fd);
    if (len < 0) return false;
    data[len] = 0;
    while (len && (data[len - 1] == '\n' || data[len - 1] == '\r')) data[--len] = 0;
    return true;
}

static bool put(const char *path, const char *data) {
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    if (fd < 0) { report("open %s: %s", path, strerror(errno)); return false; }
    size_t size = strlen(data);
    ssize_t len = write(fd, data, size);
    int saved = errno;
    close(fd);
    if (len != (ssize_t)size) { report("write %s: %s", path, strerror(saved)); return false; }
    return true;
}

static void directory(const char *path) {
    if (mkdir(path, 0755) && errno != EEXIST) report("mkdir %s: %s", path, strerror(errno));
}

static bool first_entry(const char *path, char *name, size_t size) {
    DIR *dir = opendir(path);
    if (!dir) return false;
    struct dirent *item;
    bool found = false;
    while ((item = readdir(dir))) {
        if (item->d_name[0] == '.') continue;
        snprintf(name, size, "%s", item->d_name);
        found = true;
        break;
    }
    closedir(dir);
    return found;
}

static bool setup_usb(void) {
    if (gadget_bound) return true;
    // sheng's Qualcomm glue may not create its child UDC until peripheral
    // mode is requested. Check this before waiting for /sys/class/udc.
    // Reference: anyhmos_xiaomi_sheng 8095782b, usb_setup(), USB portion only.
    const char *mode = "/sys/bus/platform/devices/a600000.ssusb/mode";
    if (!peripheral_mode_set && !access(mode, W_OK) && put(mode, "peripheral")) {
        peripheral_mode_set = true;
        report("USB Qualcomm controller switched to peripheral before UDC lookup");
    }
    char controller[256];
    if (!first_entry("/sys/class/udc", controller, sizeof(controller))) return false;
    report("UDC available: %s", controller);
    directory(GADGET);
    if (!put(GADGET "/idVendor", "0x1d6b") || !put(GADGET "/idProduct", "0x0104")) return false;
    if (!put(GADGET "/bDeviceClass", "0x02")) return false;
    if (!put(GADGET "/bcdUSB", "0x0200") || !put(GADGET "/bcdDevice", "0x0100")) return false;
    directory(GADGET "/strings/0x409");
    if (!put(GADGET "/strings/0x409/serialnumber", SHENG_DIAG_SERIAL) ||
        !put(GADGET "/strings/0x409/manufacturer", "sheng development") ||
        !put(GADGET "/strings/0x409/product", "sheng early recovery serial")) return false;
    directory(GADGET "/configs/c.1");
    directory(GADGET "/configs/c.1/strings/0x409");
    if (!put(GADGET "/configs/c.1/strings/0x409/configuration", "recovery diagnostic ACM")) return false;
    if (!put(GADGET "/configs/c.1/MaxPower", "250")) return false;
    directory(GADGET "/functions/acm.usb0");
    if (symlink(GADGET "/functions/acm.usb0", GADGET "/configs/c.1/acm.usb0") && errno != EEXIST)
        return false;
    if (!put(GADGET "/UDC", controller)) return false;
    gadget_bound = true;
    report("USB ACM bound; waiting for host DTR and GO command");
    return true;
}

static int open_serial(const char *test_tty) {
    char numbers[128];
    unsigned int major_no, minor_no;
    if (!test_tty) {
        if (!read_text("/sys/class/tty/ttyGS0/dev", numbers, sizeof(numbers)) ||
            sscanf(numbers, "%u:%u", &major_no, &minor_no) != 2) return -1;
        if (mknod("/dev/sheng_diag_serial", S_IFCHR | 0600, makedev(major_no, minor_no)) && errno != EEXIST)
            return -1;
    }
    int fd = open(test_tty ? test_tty : "/dev/sheng_diag_serial", O_RDWR | O_NOCTTY | O_NONBLOCK | O_CLOEXEC);
    if (fd >= 0) {
        struct termios attributes;
        if (!tcgetattr(fd, &attributes)) {
            cfmakeraw(&attributes);
            if (tcsetattr(fd, TCSANOW, &attributes)) report("termios: %s", strerror(errno));
        }
    }
    return fd;
}

static void cache_append(char *cache, size_t *used, size_t *sent, const char *data, size_t len) {
    if (*used + len > CACHE_SIZE) {
        const size_t drop = CACHE_SIZE / 2;
        memmove(cache, cache + drop, *used - drop);
        *used -= drop;
        *sent = *sent > drop ? *sent - drop : 0;
    }
    memcpy(cache + *used, data, len);
    *used += len;
}

static void log_to_serial(const char *source_path, const char *test_tty,
                          const char *marker_path) {
    // Only the host command GO is accepted. No shell or arbitrary command path.
    static char backlog[CACHE_SIZE];
    size_t used = 0, sent = 0;
    int source = open(source_path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    int serial = -1;
    char message[16384], command[32];
    size_t command_size = 0;
    for (;;) {
        if (report_reader >= 0) {
            ssize_t len;
            while ((len = read(report_reader, message, sizeof(message))) > 0)
                cache_append(backlog, &used, &sent, message, (size_t)len);
        }
        if (source >= 0) {
            for (unsigned int limit = 0; limit < 256; ++limit) {
                ssize_t len = read(source, message, sizeof(message));
                if (len < 0 && errno == EPIPE) continue;
                if (len <= 0) break;
                cache_append(backlog, &used, &sent, message, (size_t)len);
            }
        }
        if (serial < 0) serial = open_serial(test_tty);
        if (serial >= 0) {
            if (sent < used) {
                ssize_t len = write(serial, backlog + sent, used - sent);
                if (len > 0) sent += (size_t)len;
                else if (len < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) {
                    close(serial); serial = -1; sent = 0;
                }
            }
            if (serial >= 0) {
                ssize_t len = read(serial, message, sizeof(message));
                for (ssize_t i = 0; i < len; ++i) {
                    if (message[i] == '\n' || message[i] == '\r') {
                        command[command_size] = 0;
                        if (!strcmp(command, "GO")) {
                            int marker = open(marker_path, O_WRONLY | O_CREAT | O_CLOEXEC, 0600);
                            if (marker >= 0) close(marker);
                            report("host GO received");
                            if (test_tty) return;
                        }
                        command_size = 0;
                    } else if (command_size < sizeof(command) - 1) command[command_size++] = message[i];
                }
            }
        }
        usleep(20000);
    }
}

static void mount_firmware(void) {
    char cmdline[8192], slot[4] = "", path[1024], text[2048], numbers[128];
    if (read_text("/proc/cmdline", cmdline, sizeof(cmdline))) {
        const char *start = strstr(cmdline, "androidboot.slot_suffix=");
        if (start) snprintf(slot, sizeof(slot), "%.2s", start + strlen("androidboot.slot_suffix="));
    }
    if (strcmp(slot, "_a") && strcmp(slot, "_b")) { report("no valid slot; firmware not mounted"); return; }
    DIR *dir = opendir("/sys/class/block");
    if (!dir) return;
    struct dirent *item;
    char partname[64];
    snprintf(partname, sizeof(partname), "PARTNAME=modem%s", slot);
    while ((item = readdir(dir))) {
        if (item->d_name[0] == '.') continue;
        snprintf(path, sizeof(path), "/sys/class/block/%s/uevent", item->d_name);
        if (!read_text(path, text, sizeof(text)) || !strstr(text, partname)) continue;
        snprintf(path, sizeof(path), "/sys/class/block/%s/dev", item->d_name);
        unsigned int major_no, minor_no;
        if (!read_text(path, numbers, sizeof(numbers)) || sscanf(numbers, "%u:%u", &major_no, &minor_no) != 2) continue;
        if (mknod("/dev/sheng_diag_modem", S_IFBLK | 0600, makedev(major_no, minor_no)) && errno != EEXIST) break;
        directory("/firmware");
        if (mount("/dev/sheng_diag_modem", "/firmware", "vfat", MS_RDONLY | MS_NOSUID | MS_NODEV, ""))
            report("read-only modem mount: %s", strerror(errno));
        else {
            report("mounted modem%s read-only for USB/ADSP firmware", slot);
            if (!put("/sys/module/firmware_class/parameters/path", "/firmware/image")) break;
            DIR *remotes = opendir("/sys/class/remoteproc");
            if (remotes) {
                struct dirent *remote;
                while ((remote = readdir(remotes))) {
                    if (remote->d_name[0] == '.') continue;
                    snprintf(path, sizeof(path), "/sys/class/remoteproc/%s/name", remote->d_name);
                    if (!read_text(path, text, sizeof(text)) || !strstr(text, "adsp")) continue;
                    snprintf(path, sizeof(path), "/sys/class/remoteproc/%s/state", remote->d_name);
                    if (read_text(path, text, sizeof(text)) && !strcmp(text, "offline") &&
                        !access("/firmware/image/adsp.mdt", R_OK) && !access("/firmware/image/adsp.b01", R_OK))
                        put(path, "start");
                }
                closedir(remotes);
            }
        }
        break;
    }
    closedir(dir);
}

static void parse_runtime_options(const char *, const char *, const char *, char *, size_t);

static int self_test(void) {
    if (getpid() == 1) return 1;
    char options[1024];
    parse_runtime_options("/lib/modules/example/msm_drm.ko", "", 
        "androidboot.hardware=qcom msm_drm.dsi_display0=qcom,correct-panel:config0 msm-drm.example=\"two words\" mtdoops.mtddev=0",
        options, sizeof(options));
    if (strcmp(options, "dsi_display0=qcom,correct-panel:config0 example=\"two words\"")) return 3;
    parse_runtime_options("/lib/modules/mtdoops.ko", "", "mtdoops.mtddev=0", options, sizeof(options));
    if (strcmp(options, "mtddev=0")) return 4;
    parse_runtime_options("/lib/modules/other.ko", "fallback=1", "androidboot.hardware=qcom", options, sizeof(options));
    if (strcmp(options, "fallback=1")) return 5;
    printf("sheng diagnostic r4: static executable self-test OK; pid=%ld; NO mounts/modules/USB writes\n", (long)getpid());
    return 0;
}

static void parse_runtime_options(const char *module_path, const char *fallback, const char *text,
                                  char *result, size_t size) {
    char cmdline[32768], module[256];
    const char *base = strrchr(module_path, '/');
    const char *name = base ? base + 1 : module_path;
    if (strlen(name) >= sizeof(module) || strlen(text) >= sizeof(cmdline)) {
        snprintf(result, size, "%s", fallback);
        return;
    }
    memcpy(module, name, strlen(name) + 1);
    memcpy(cmdline, text, strlen(text) + 1);
    char *suffix = strstr(module, ".ko");
    if (suffix) *suffix = 0;
    for (char *p = module; *p; ++p) if (*p == '-') *p = '_';
    result[0] = 0;
    {
        char *start = cmdline;
        while (*start) {
            while (*start == ' ') ++start;
            if (!*start) break;
            char *end = start;
            bool quoted = false;
            while (*end && (*end != ' ' || quoted)) { if (*end == '"') quoted = !quoted; ++end; }
            char saved = *end;
            *end = 0;
            char *dot = strchr(start, '.');
            char *equals = strchr(start, '=');
            if (dot && equals && dot < equals) {
                *dot = 0;
                for (char *p = start; *p; ++p) if (*p == '-') *p = '_';
                if (!strcmp(start, module)) {
                    size_t used = strlen(result), needed = strlen(dot + 1);
                    if (used + needed + 2 < size) {
                        if (used) result[used++] = ' ';
                        memcpy(result + used, dot + 1, needed + 1);
                    }
                }
            }
            if (!saved) break;
            start = end + 1;
        }
    }
    if (!result[0]) snprintf(result, size, "%s", fallback);
}

static void runtime_options(const char *module_path, const char *fallback, char *result, size_t size) {
    char cmdline[32768] = "";
    read_text("/proc/cmdline", cmdline, sizeof(cmdline));
    parse_runtime_options(module_path, fallback, cmdline, result, size);
}

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--self-test")) return self_test();
    if (argc == 5 && !strcmp(argv[1], "--transport-test") && getpid() != 1 &&
        !strncmp(argv[2], "/tmp/sheng-", 11) && !strncmp(argv[3], "/dev/pts/", 9) &&
        !strncmp(argv[4], "/tmp/sheng-", 11)) {
        log_to_serial(argv[2], argv[3], argv[4]);
        return 0;
    }
    if (getpid() != 1) { fputs("Diagnostic init must be PID 1; no action performed.\n", stderr); return 2; }
    umask(022);
    directory("/dev"); directory("/proc"); directory("/sys"); directory("/config"); directory("/diag-run");
    if (mount("tmpfs", "/dev", "tmpfs", MS_NOSUID, "mode=0755")) perror("mount /dev");
    if (mount("proc", "/proc", "proc", 0, "")) perror("mount /proc");
    if (mount("sysfs", "/sys", "sysfs", 0, "")) perror("mount /sys");
    if (mount("configfs", "/config", "configfs", 0, "")) perror("mount /config");
    if (mount("tmpfs", "/diag-run", "tmpfs", MS_NOSUID | MS_NODEV, "mode=0755")) perror("mount /diag-run");
    if (mknod("/dev/kmsg", S_IFCHR | 0600, makedev(1, 11)) && errno != EEXIST) perror("mknod kmsg");
    kernel_log = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);
    signal(SIGPIPE, SIG_IGN);
    int report_pipe[2];
    if (!pipe2(report_pipe, O_CLOEXEC | O_NONBLOCK)) {
        report_reader = report_pipe[0]; report_writer = report_pipe[1];
    }
    struct utsname uts;
    if (!uname(&uts)) report("STATIC PID1 START kernel=%s", uts.release);
    char bootargs[16384];
    if (read_text("/proc/cmdline", bootargs, sizeof(bootargs))) report("BOOTARGS: %s", bootargs);
    report("diagnostic userspace performs no flash/format operations; modem mount is read-only");
    signal(SIGCHLD, SIG_IGN);
    pid_t logger = fork();
    if (!logger) log_to_serial("/dev/kmsg", NULL, "/diag-run/continue");
    if (logger < 0) report("logger fork: %s", strerror(errno));
    FILE *list = fopen("/diag/module-order", "re");
    char path[1024];
    unsigned int sequence = 0, failures = 0;
    if (list) {
        while (fgets(path, sizeof(path), list)) {
            path[strcspn(path, "\r\n")] = 0;
            if (!path[0] || path[0] == '#') continue;
            char *parameters = strchr(path, '\t');
            if (parameters) *parameters++ = 0;
            else parameters = "";
            char actual_parameters[4096];
            runtime_options(path, parameters, actual_parameters, sizeof(actual_parameters));
            report("module %u BEFORE %s options=[%s]", ++sequence, path, actual_parameters);
            int fd = open(path, O_RDONLY | O_CLOEXEC);
            int result = fd < 0 ? -1 : (int)syscall(SYS_finit_module, fd, actual_parameters, 0);
            int saved = errno;
            if (fd >= 0) close(fd);
            if (result && saved != EEXIST) {
                ++failures;
                report("module %u FAILED errno=%d %s", sequence, saved, strerror(saved));
            } else report("module %u OK%s", sequence, result ? " already loaded" : "");
            setup_usb();
        }
        fclose(list);
    } else report("module-order unavailable: %s", strerror(errno));
    report("module pass complete: count=%u failures=%u; errors retained, not a success claim", sequence, failures);
    mount_firmware();
    if (!access("/sys/bus/platform/devices/a600000.ssusb/mode", W_OK))
        put("/sys/bus/platform/devices/a600000.ssusb/mode", "peripheral");
    for (unsigned int i = 0; i < 300 && !gadget_bound; ++i) { setup_usb(); usleep(100000); }
    report("HOLD before Android init. Serial collector sends GO after opening the COM port.");
    // Never blindly continue/reboot before a host has had a chance to capture.
    while (access("/diag-run/continue", F_OK)) sleep(1);
    report("HANDOFF to original %s; early logger remains attached", SHENG_DIAG_INIT);
    // Android first-stage mounts sysfs itself and treats EBUSY as fatal. Its
    // diagnostic predecessor must detach its mounts before transferring PID1.
    struct statfs remaining;
    for (unsigned int layer = 0; layer < 8; ++layer) {
        if (statfs("/sys", &remaining) || remaining.f_type != 0x62656572) break;
        int result = umount2("/sys", MNT_DETACH);
        report("sysfs detach layer=%u result=%d errno=%d", layer, result, result ? errno : 0);
        if (result) break;
    }
    if (!statfs("/sys", &remaining) && remaining.f_type == 0x62656572) {
        report("HANDOFF REFUSED: sysfs is still mounted; preserving serial instead of init panic");
        for (;;) sleep(1);
    }
    if (umount2("/proc", MNT_DETACH)) report("detach diagnostic procfs: %s", strerror(errno));
    signal(SIGCHLD, SIG_DFL);
    signal(SIGPIPE, SIG_DFL);
    char *const args[] = { "/init", NULL };
    char *const environment[] = { "PATH=/system/bin:/system/xbin", "SHENG_DIAG=1", NULL };
    execve(SHENG_DIAG_INIT, args, environment);
    report("exec original init FAILED: %s", strerror(errno));
    for (;;) sleep(1);
}
