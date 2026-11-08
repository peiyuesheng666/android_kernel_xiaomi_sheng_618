// SPDX-License-Identifier: Apache-2.0
// Leave stock init and its module order running; capture USB logs separately.
#define main sheng_legacy_serial_main
#include "../../../rootdir/recovery/serial_init.c"
#undef main
#include <sched.h>

static void background_capture(void) {
    // Do not leave mounts for first-stage init to trip over. Root mount
    // propagation must be private before mounting the logger's own /dev/sys.
    if (unshare(CLONE_NEWNS) || mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL)) _exit(20);
    directory("/dev"); directory("/proc"); directory("/sys"); directory("/config");
    if (mount("tmpfs", "/dev", "tmpfs", MS_NOSUID, "mode=0755") ||
        mount("proc", "/proc", "proc", 0, "") ||
        mount("sysfs", "/sys", "sysfs", 0, "") ||
        mount("configfs", "/config", "configfs", 0, "")) _exit(21);
    if (mknod("/dev/kmsg", S_IFCHR | 0600, makedev(1, 11)) && errno != EEXIST) _exit(22);
    kernel_log = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);
    signal(SIGPIPE, SIG_IGN);
    struct utsname uts;
    if (!uname(&uts)) report("SHENG618 BACKGROUND LOGGER kernel=%s; stock init runs concurrently", uts.release);
    pid_t transport = fork();
    if (!transport) log_to_serial("/dev/kmsg", NULL, "/dev/sheng_unused_go");
    if (transport < 0) _exit(23);
    // The normal 6.18 module loader, not this process, supplies USB drivers.
    for (unsigned int i = 0; i < 1200 && !gadget_bound; ++i) {
        setup_usb();
        usleep(100000);
    }
    if (gadget_bound) report("BACKGROUND USB serial ready; no init hold and no GO required");
    for (;;) pause();
}

int main(int argc, char **argv) {
    if (getpid() != 1) return sheng_legacy_serial_main(argc, argv);
    pid_t capture = fork();
    if (!capture) background_capture();
    char *const original[] = { "/init", NULL };
    execv(SHENG_DIAG_INIT, original);
    // Preserve an observable failure if the stock generic ramdisk lacks init.
    for (;;) pause();
}
