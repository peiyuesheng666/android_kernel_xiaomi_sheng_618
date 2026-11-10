/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SHENG_NANOSIC_CONNECTION_H
#define SHENG_NANOSIC_CONNECTION_H

/* The A2 layout and connection masks match shipping nanosic_platform. */
enum sheng_nano_connection {
	SHENG_NANO_NO_UPDATE = -1,
	SHENG_NANO_DISCONNECTED,
	SHENG_NANO_KEYBOARD,
	SHENG_NANO_DOCK,
};

static inline int sheng_nano_connection_state(const unsigned char *report,
					     unsigned long length)
{
	unsigned char state;

	if (!report || length < 11 ||
	    (report[0] != 0x22 && report[0] != 0x23 && report[0] != 0x24) ||
	    report[1] != 0x31 || report[2] != 0x38 || report[3] != 0x80 ||
	    report[4] != 0xa2 || report[7] != 0)
		return SHENG_NANO_NO_UPDATE;
	state = report[9];
	if (((state & 0x03) == 0x03 || (state & 0x03) == 0x01) &&
	    (state & 0x60) == 0x20)
		return SHENG_NANO_KEYBOARD;
	if ((state & 0x03) == 0 && (state & 0x68) == 0x28)
		return SHENG_NANO_DOCK;
	return SHENG_NANO_DISCONNECTED;
}
#endif
