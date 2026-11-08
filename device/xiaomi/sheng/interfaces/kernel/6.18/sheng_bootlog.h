/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _LINUX_SHENG_BOOTLOG_H
#define _LINUX_SHENG_BOOTLOG_H

#ifdef CONFIG_SHENG_BOOTLOG
void sheng_bootlog_fault_pause(void);
#else
static inline void sheng_bootlog_fault_pause(void) { }
#endif

#endif
