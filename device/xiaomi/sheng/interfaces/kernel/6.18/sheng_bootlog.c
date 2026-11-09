// SPDX-License-Identifier: GPL-2.0-only
// Built-in boot log snapshots for this sheng's 300 MiB rawdump partition.
// Reference: selected SM8550 integration k618_probe.c (partition validation,
// alternating snapshots). No USB, filesystem mounts, or module helper needed.
#include <linux/blkdev.h>
#include <linux/atomic.h>
#include <linux/crc32.h>
#include <linux/cpumask.h>
#include <linux/device.h>
#include <linux/delay.h>
#include <linux/err.h>
#include <linux/file.h>
#include <linux/fs.h>
#include <linux/hrtimer.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/kmsg_dump.h>
#include <linux/ktime.h>
#include <linux/kthread.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/nvmem-consumer.h>
#include <linux/of.h>
#include <linux/random.h>
#include <linux/reboot.h>
#include <linux/sched/debug.h>
#include <linux/sched/signal.h>
#include <linux/sheng_bootlog.h>
#include <linux/smp.h>
#include <linux/string.h>
#include <linux/vmalloc.h>
#include <linux/workqueue.h>

#define PART_BYTES (300ULL * 1024 * 1024)
#define LOG_OFFSET (288ULL * 1024 * 1024)
#define SLOT_BYTES (1024U * 1024)
#define LIFE_MS 120000
#define STEADY_INTERVAL_MS 10000
#define EARLY_TRACE_BYTES (128U * 1024)

struct bootlog_header {
    char magic[8];
    __le32 version, header_bytes;
    __le64 run, sequence, uptime_ms;
    __le32 text_bytes, text_crc, total_bytes, reserved;
    char padding[8];
} __packed;

struct bootlog_end {
    char magic[8];
    __le64 sequence;
} __packed;

static bool enabled = true;
module_param_named(enable, enabled, bool, 0400);
/* Test builds opt in on the command line; normal builds never reboot here. */
static unsigned int test_timeout;
module_param(test_timeout, uint, 0400);
/* Opt-in stage isolation before Android init loads board driver modules. */
static unsigned int pre_driver_hold_ms;
module_param(pre_driver_hold_ms, uint, 0400);
static char revision[65] = "unspecified";
module_param_string(revision, revision, sizeof(revision), 0400);
static unsigned long next_identity;
static atomic_t restart_requested = ATOMIC_INIT(0);
static struct task_struct *test_reset_task;
static struct hrtimer restart_guard;
static struct file *destination;
static char *snapshot;
/* Bounded boot diagnostics survive later printk storms in both disk slots.
 * Read only kernel messages already published through printk. Never access
 * input samples, biometric templates or camera buffers here.
 */
static char early_trace[EARLY_TRACE_BYTES];
static size_t early_trace_bytes;
static u64 early_next_seq;
static u64 run_id, sequence;
static unsigned long began;
static void save_snapshot(struct work_struct *work);
static void save_fault_snapshot(struct work_struct *work);
static DECLARE_DELAYED_WORK(snapshot_work, save_snapshot);
static DECLARE_WORK(fault_work, save_fault_snapshot);
static DEFINE_MUTEX(snapshot_lock);
static atomic_t fault_pause_used = ATOMIC_INIT(0);

bool sheng_bootlog_test_mode(void)
{
    return enabled && test_timeout >= 10 && test_timeout <= 600;
}

void sheng_bootlog_panic_pause(void)
{
    /* Normal builds also need panic logs; automatic reset stays test-only. */
    sheng_bootlog_fault_pause();
}

/* Same DT cell and value as the board's qcom-reboot-reason driver. No raw
 * physical address or guessed PMIC register; retry until its provider probes.
 * Prearming permits the emergency restart path to avoid sleepable NVMEM I/O.
 */
static bool arm_bootloader_reason(void)
{
    struct device_node *node;
    struct nvmem_cell *cell;
    u8 reason = 0x02;
    int result;

    node = of_find_compatible_node(NULL, NULL, "qcom,reboot-reason");
    if (!node)
        return false;
    cell = of_nvmem_cell_get(node, "restart_reason");
    of_node_put(node);
    if (IS_ERR(cell))
        return false;
    result = nvmem_cell_write(cell, &reason, sizeof(reason));
    nvmem_cell_put(cell);
    if (result != sizeof(reason))
        return false;
    pr_notice("sheng_bootlog: test bootloader PMIC reason 0x02 armed\n");
    return true;
}

/* Called by arm64 __die after the real registers/stack have been printed.
 * Never do block I/O or acquire a logger lock from the exception context.
 * Explicitly wake a writer on another online CPU; the delayed work's timer
 * may be pinned to the CPU that has just disabled its interrupts.
 * This cannot help if the storage IRQ is on the faulting CPU, or the SoC
 * hangs without entering __die. Keep the delay bounded and one-shot.
 */
void sheng_bootlog_fault_pause(void)
{
    unsigned int cpu;

    if (!READ_ONCE(destination) || atomic_cmpxchg(&fault_pause_used, 0, 1))
        return;
    cpu = cpumask_any_but(cpu_online_mask, raw_smp_processor_id());
    if (cpu >= nr_cpu_ids)
        return;
    pr_emerg("sheng_bootlog: exception registers/stack printed; 1500 ms capture window on CPU%u\n", cpu);
    queue_work_on(cpu, system_highpri_wq, &fault_work);
    /* Leave other CPUs alive long enough to persist and perform a test reset. */
    mdelay(test_timeout ? 15000 : 1500);
}

static int is_rawdump(struct device *dev, const void *unused)
{
    struct block_device *bdev = dev_to_bdev(dev);

    return bdev->bd_meta_info &&
        !strcmp(bdev->bd_meta_info->volname, "rawdump") &&
        bdev_nr_bytes(bdev) == PART_BYTES;
}

static void open_destination(void)
{
    struct device *dev;
    struct file *file;
    struct block_device *bdev;

    // Walk the in-kernel block-device registry, even before init creates /dev.
    dev = class_find_device(&block_class, NULL, NULL, is_rawdump);
    if (!dev)
        return;
    file = bdev_file_open_by_dev(dev->devt, BLK_OPEN_WRITE, NULL, NULL);
    put_device(dev);
    if (IS_ERR(file))
        return;
    bdev = file_bdev(file);
    // Revalidate the opened handle, not merely the device found above.
    if (!bdev->bd_meta_info || strcmp(bdev->bd_meta_info->volname, "rawdump") ||
        bdev_nr_bytes(bdev) != PART_BYTES ||
        LOG_OFFSET + 2ULL * SLOT_BYTES > bdev_nr_bytes(bdev)) {
        fput(file);
        return;
    }
    destination = file;
    pr_notice("sheng_bootlog: rawdump %u:%u, bounded region 288..290 MiB\n",
              MAJOR(bdev->bd_dev), MINOR(bdev->bd_dev));
}

/* snapshot_lock serializes the regular and remote fault workers. */
static void capture_early_trace(void)
{
    struct kmsg_dump_iter iter;
    char line[1024];
    size_t bytes;
    unsigned int budget = 4096;

    if (early_trace_bytes >= EARLY_TRACE_BYTES - sizeof(line))
        return;
    kmsg_dump_rewind(&iter);
    iter.cur_seq = max(iter.cur_seq, early_next_seq);
    while (budget-- && kmsg_dump_get_line(&iter, true, line, sizeof(line), &bytes)) {
        /* get_line returns a byte count, not a guaranteed C string. */
        line[min(bytes, sizeof(line) - 1)] = '\0';
        if (strstr(line, "NVT-ts") || strstr(line, "ktz8866") ||
            strstr(line, "sheng_backlight") || strstr(line, "fpc1020") ||
            strstr(line, "sheng-hall") || strstr(line, "xiaomi_hall") ||
            strstr(line, "nanosic_driver 5-004c:") || strstr(line, "sheng_nanosic") ||
            strstr(line, "k618_load:") || strstr(line, "init first stage") ||
            strstr(line, "init second stage") || strstr(line, "Wait for '") ||
            strstr(line, "Direct firmware load") ||
            strstr(line, "SHENG_EARLY_TRACE_TEST")) {
            bytes = min(bytes, sizeof(line) - 1);
            if (bytes > EARLY_TRACE_BYTES - early_trace_bytes)
                break;
            memcpy(early_trace + early_trace_bytes, line, bytes);
            early_trace_bytes += bytes;
        }
    }
    early_next_seq = iter.cur_seq;
}

static void capture_snapshot(void)
{
    struct kmsg_dump_iter iter;
    struct bootlog_header *header;
    struct bootlog_end *end;
    loff_t position;
    size_t text_bytes = 0, total;
    ssize_t written;
    int error;

    capture_early_trace();
    if (!destination)
        open_destination();
    if (!destination)
        return;
    if (time_after_eq(jiffies, next_identity)) {
        pr_notice("sheng_bootlog: identity revision=%s run=%016llx\n", revision, run_id);
        next_identity = jiffies + msecs_to_jiffies(1000);
    }
    memset(snapshot, 0, SLOT_BYTES);
    kmsg_dump_rewind(&iter);
    kmsg_dump_get_buffer(&iter, true, snapshot + sizeof(*header),
                        SLOT_BYTES - sizeof(*header) - sizeof(*end) - 4095 - 512 - early_trace_bytes,
                        &text_bytes);
    text_bytes += scnprintf(snapshot + sizeof(*header) + text_bytes, 128,
                           "\nsheng_bootlog: preserved early driver trace begin\n");
    memcpy(snapshot + sizeof(*header) + text_bytes, early_trace, early_trace_bytes);
    text_bytes += early_trace_bytes;
    text_bytes += scnprintf(snapshot + sizeof(*header) + text_bytes, 128,
                           "\nsheng_bootlog: preserved early driver trace end\n");
    /* Keep identity inside the CRC-covered payload even under a printk storm. */
    text_bytes += scnprintf(snapshot + sizeof(*header) + text_bytes, 256,
                           "\nsheng_bootlog: identity revision=%s run=%016llx\n",
                           revision, run_id);
    total = ALIGN(sizeof(*header) + text_bytes + sizeof(*end), 4096);
    header = (struct bootlog_header *)snapshot;
    memcpy(header->magic, "SH618LOG", 8);
    header->version = cpu_to_le32(1);
    header->header_bytes = cpu_to_le32(sizeof(*header));
    header->run = cpu_to_le64(run_id);
    header->sequence = cpu_to_le64(++sequence);
    header->uptime_ms = cpu_to_le64(ktime_get_boottime_ns() / NSEC_PER_MSEC);
    header->text_bytes = cpu_to_le32(text_bytes);
    header->text_crc = cpu_to_le32(crc32_le(~0U, snapshot + sizeof(*header), text_bytes) ^ ~0U);
    header->total_bytes = cpu_to_le32(total);
    end = (struct bootlog_end *)(snapshot + total - sizeof(*end));
    memcpy(end->magic, "SH618END", 8);
    end->sequence = header->sequence;
    position = LOG_OFFSET + (sequence & 1) * SLOT_BYTES;
    written = __kernel_write(destination, snapshot, total, &position);
    error = written == total ? vfs_fsync(destination, 1) : -EIO;
    if (error)
        pr_err_ratelimited("sheng_bootlog: snapshot %llu write/flush failed %zd/%zu err=%d\n",
                           sequence, written, total, error);
    else if (sequence == 1)
        pr_notice("sheng_bootlog: first snapshot persisted, %zu bytes\n", text_bytes);
}

static void save_fault_snapshot(struct work_struct *work)
{
    unsigned long until = jiffies + msecs_to_jiffies(1000);

    while (!mutex_trylock(&snapshot_lock)) {
        if (time_after_eq(jiffies, until))
            return;
        msleep(10);
    }
    if (snapshot && destination)
        capture_snapshot();
    mutex_unlock(&snapshot_lock);
    if (test_timeout) {
        unsigned int cpu = get_cpu();

        put_cpu();
        /* Their previous sleep timer may be pinned to the exception CPU,
         * whose IRQs are now off. Move and wake them on the capture CPU.
         */
        atomic_set(&restart_requested, 1);
        if (!IS_ERR_OR_NULL(test_reset_task)) {
            set_cpus_allowed_ptr(test_reset_task, cpumask_of(cpu));
            wake_up_process(test_reset_task);
        }
    }
}

static void save_test_stacks(struct work_struct *work)
{
    struct task_struct *task;

    pr_emerg("sheng_bootlog: test deadline diagnostics: init and blocked tasks\n");
    rcu_read_lock();
    task = find_task_by_vpid(1);
    if (task)
        get_task_struct(task);
    rcu_read_unlock();
    if (task) {
        sched_show_task(task);
        put_task_struct(task);
    }
    show_state_filter(TASK_UNINTERRUPTIBLE);
    /* The independent reset thread does not wait for this I/O or task dump. */
    mutex_lock(&snapshot_lock);
    if (snapshot)
        capture_snapshot();
    mutex_unlock(&snapshot_lock);
}
static DECLARE_WORK(test_stacks_work, save_test_stacks);

static int test_restart(void *unused)
{
    bool dumped = false;
    bool reason_armed = false;
    u64 last_reason_try = 0;

    for (;;) {
        u64 seconds = ktime_get_boottime_seconds();

        if (!reason_armed && seconds >= last_reason_try + 2) {
            last_reason_try = seconds;
            reason_armed = arm_bootloader_reason();
        }
        if (!dumped && seconds + 5 >= test_timeout) {
            dumped = true;
            queue_work(system_unbound_wq, &test_stacks_work);
        }
        if (seconds >= test_timeout || atomic_read(&restart_requested))
            break;
        msleep(100);
    }
    pr_emerg("sheng_bootlog: TEST_RETURN_BOOTLOADER timeout=%u fault=%d\n",
             test_timeout, atomic_read(&restart_requested));
    /* Arm an independent high resolution timer before shutdown can block.
     * Board notifier qcom-reboot-reason (priority 255) writes PMIC reason 0x02.
     */
    hrtimer_start(&restart_guard, ms_to_ktime(10000), HRTIMER_MODE_REL_PINNED);
    kernel_restart("bootloader");
    return 0;
}

static enum hrtimer_restart test_restart_fallback(struct hrtimer *timer)
{
    pr_emerg("sheng_bootlog: TEST_RETURN_BOOTLOADER shutdown stalled; architecture reset\n");
    /* Do not acquire driver shutdown locks a second time. The normal path
     * must have reached its PMIC notifier for bootloader intent to persist.
     */
    machine_restart("bootloader");
    return HRTIMER_NORESTART;
}

static void save_snapshot(struct work_struct *work)
{
    bool fast;
    unsigned int interval;

    mutex_lock(&snapshot_lock);
    capture_snapshot();
    fast = time_before(jiffies, began + msecs_to_jiffies(
            test_timeout ? (test_timeout + 20) * 1000 : LIFE_MS));
    /* Keep the bounded slots and exception writer available after boot.
     * Slow down steady-state I/O instead of losing every late fault.
     */
    interval = fast ? (destination ? 250 : 100) : STEADY_INTERVAL_MS;
    queue_delayed_work(system_unbound_wq, &snapshot_work, msecs_to_jiffies(interval));
    mutex_unlock(&snapshot_lock);
}

static int __init sheng_bootlog_init(void)
{
    static_assert(sizeof(struct bootlog_header) == 64);
    static_assert(sizeof(struct bootlog_end) == 16);
    if (!enabled)
        return 0;
    if (test_timeout && (test_timeout < 10 || test_timeout > 600))
        return -EINVAL;
    if (pre_driver_hold_ms > 10000)
        return -EINVAL;
    if (pre_driver_hold_ms) {
        pr_notice("sheng_bootlog: TEST_ONLY pre-driver hold begin (%u ms)\n",
                  pre_driver_hold_ms);
        msleep(pre_driver_hold_ms);
        pr_notice("sheng_bootlog: TEST_ONLY pre-driver hold end\n");
    }
    snapshot = vzalloc(SLOT_BYTES);
    if (!snapshot)
        return -ENOMEM;
    run_id = get_random_u64();
    began = jiffies;
    pr_notice("sheng_bootlog: built-in capture armed, run %016llx; waiting for rawdump\n", run_id);
    queue_delayed_work(system_unbound_wq, &snapshot_work, msecs_to_jiffies(100));
    if (test_timeout) {
        struct task_struct *reset;

        hrtimer_setup(&restart_guard, test_restart_fallback, CLOCK_MONOTONIC,
                      HRTIMER_MODE_REL_PINNED);
        reset = kthread_run(test_restart, NULL, "sheng-test");
        test_reset_task = reset;
        if (IS_ERR(reset)) {
            pr_err("sheng_bootlog: test restart thread failed\n");
            return PTR_ERR(reset);
        }
        pr_notice("sheng_bootlog: TEST_ONLY automatic bootloader return at uptime %u seconds\n",
                  test_timeout);
    }
    return 0;
}
late_initcall(sheng_bootlog_init);
