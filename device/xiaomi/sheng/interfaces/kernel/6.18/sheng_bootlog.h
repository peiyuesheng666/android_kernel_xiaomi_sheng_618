/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _LINUX_SHENG_BOOTLOG_H
#define _LINUX_SHENG_BOOTLOG_H

#include <linux/types.h>

#ifdef CONFIG_SHENG_BOOTLOG
void sheng_bootlog_fault_pause(void);
bool sheng_bootlog_test_mode(void);
void sheng_bootlog_panic_pause(void);
#else
static inline void sheng_bootlog_fault_pause(void) { }
static inline bool sheng_bootlog_test_mode(void) { return false; }
static inline void sheng_bootlog_panic_pause(void) { }
#endif

#endif
