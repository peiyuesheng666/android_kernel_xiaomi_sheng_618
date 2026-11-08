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
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/kmsg_dump.h>
#include <linux/ktime.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/random.h>
#include <linux/sheng_bootlog.h>
#include <linux/smp.h>
#include <linux/string.h>
#include <linux/vmalloc.h>
#include <linux/workqueue.h>

#define PART_BYTES (300ULL * 1024 * 1024)
#define LOG_OFFSET (288ULL * 1024 * 1024)
#define SLOT_BYTES (1024U * 1024)
#define LIFE_MS 120000

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
static struct file *destination;
static char *snapshot;
static u64 run_id, sequence;
static unsigned long began;
static void save_snapshot(struct work_struct *work);
static void save_fault_snapshot(struct work_struct *work);
static DECLARE_DELAYED_WORK(snapshot_work, save_snapshot);
static DECLARE_WORK(fault_work, save_fault_snapshot);
static DEFINE_MUTEX(snapshot_lock);
static atomic_t fault_pause_used = ATOMIC_INIT(0);

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
    mdelay(1500);
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
static void capture_snapshot(void)
{
    struct kmsg_dump_iter iter;
    struct bootlog_header *header;
    struct bootlog_end *end;
    loff_t position;
    size_t text_bytes = 0, total;
    ssize_t written;
    int error;

    if (!destination)
        open_destination();
    if (!destination)
        return;
    memset(snapshot, 0, SLOT_BYTES);
    kmsg_dump_rewind(&iter);
    kmsg_dump_get_buffer(&iter, true, snapshot + sizeof(*header),
                        SLOT_BYTES - sizeof(*header) - sizeof(*end) - 4095,
                        &text_bytes);
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
}

static void save_snapshot(struct work_struct *work)
{
    mutex_lock(&snapshot_lock);
    capture_snapshot();
    if (time_before(jiffies, began + msecs_to_jiffies(LIFE_MS)))
        queue_delayed_work(system_unbound_wq, &snapshot_work,
                           msecs_to_jiffies(destination ? 250 : 100));
    else {
        if (destination)
            fput(destination);
        destination = NULL;
        vfree(snapshot);
        snapshot = NULL;
        pr_notice("sheng_bootlog: finished after 120 seconds\n");
    }
    mutex_unlock(&snapshot_lock);
}

static int __init sheng_bootlog_init(void)
{
    static_assert(sizeof(struct bootlog_header) == 64);
    static_assert(sizeof(struct bootlog_end) == 16);
    if (!enabled)
        return 0;
    snapshot = vzalloc(SLOT_BYTES);
    if (!snapshot)
        return -ENOMEM;
    run_id = get_random_u64();
    began = jiffies;
    pr_notice("sheng_bootlog: built-in capture armed, run %016llx; waiting for rawdump\n", run_id);
    queue_delayed_work(system_unbound_wq, &snapshot_work, msecs_to_jiffies(100));
    return 0;
}
late_initcall(sheng_bootlog_init);
