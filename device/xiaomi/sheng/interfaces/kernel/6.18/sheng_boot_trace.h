/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SHENG_BOOT_TRACE_H
#define SHENG_BOOT_TRACE_H
#include <linux/delay.h>
#include <linux/printk.h>

/* Diagnostic image only. Call only from sleepable display probe context.
 * Give the 250 ms rawdump worker time to persist the last completed stage.
 */
static inline void sheng_probe_checkpoint(const char *stage)
{
	pr_notice("sheng_display_probe: %s\n", stage);
	msleep(350);
}
#endif
