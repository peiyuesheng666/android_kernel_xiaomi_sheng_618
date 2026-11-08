/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _SHENG_RPMSG_H
#define _SHENG_RPMSG_H
#include <linux/rpmsg.h>

/* LOS GLINK extensions use private channel storage, preserving ACK's ABI. */
#define RPMSG_HANDLED 0
#define RPMSG_DEFER 1
typedef int (*sheng_rpmsg_rx_sig_t)(struct rpmsg_device *, void *, u32, u32);
int rpmsg_rx_done(struct rpmsg_endpoint *ept, void *data);
int rpmsg_get_signals(struct rpmsg_endpoint *ept);
int rpmsg_set_signals(struct rpmsg_endpoint *ept, u32 set, u32 clear);
bool sheng_rpmsg_supports_rx_done(struct rpmsg_endpoint *ept);
int sheng_rpmsg_set_signals_callback(struct rpmsg_endpoint *ept, sheng_rpmsg_rx_sig_t callback);
#endif
