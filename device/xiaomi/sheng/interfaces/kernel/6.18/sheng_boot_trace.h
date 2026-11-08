/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SHENG_BOOT_TRACE_H
#define SHENG_BOOT_TRACE_H
#include <linux/printk.h>

/* Keep diagnostic stage markers without delaying normal boot. */
static inline void sheng_probe_checkpoint(const char *stage)
{
	pr_notice("sheng_display_probe: %s\n", stage);
}
#endif
