/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SHENG_PEN_CONTACT_H
#define SHENG_PEN_CONTACT_H

struct sheng_pen_contact {
	unsigned long long last_down_ns;
	unsigned int previous_sequence;
	unsigned int have_sequence;
};

static inline unsigned int sheng_pen_u16(const unsigned char *p)
{
	return p[0] | (unsigned int)p[1] << 8;
}

static inline unsigned int sheng_pen_u32(const unsigned char *p)
{
	return sheng_pen_u16(p) | sheng_pen_u16(p + 2) << 16;
}

static inline void sheng_pen_put16(unsigned char *p, unsigned int value)
{
	p[0] = value;
	p[1] = value >> 8;
}

static inline unsigned int sheng_pen_checksum(const unsigned char *p,
		unsigned int words)
{
	unsigned int sum = 0, i;

	for (i = 0; i < words * 2; i++)
		sum += sheng_pen_u16(p + 20 + i * 2);
	return -sum & 0xffff;
}

/* N81A P81c type 29 contains a digital contact flag, not the BLE pressure.
 * Captured continuous strokes have 12-29 ms gaps in this flag, while the
 * tip/ring matrices and BLE pressure stream continue. Bridge at most 32 ms
 * from an actual contact, only with consecutive, checksum-valid packets.
 * Never extend the deadline using a repaired packet. No coordinates, sensor
 * matrices, BLE pressure or sustained hover values are manufactured here.
 */
static inline int sheng_pen_filter_contact(struct sheng_pen_contact *state,
		unsigned char *p, unsigned int size, unsigned long long now_ns,
		unsigned int hold_ms)
{
	unsigned int sequence, pressure, checksum;

	if (!hold_ms || hold_ms > 32 || size < 5160 || p[0] != 0xa5 ||
		sheng_pen_u32(p + 8) != 0x505 || p[56] != 29 ||
		p[71] != 12 || p[72] != 40 || p[73] != 60 || p[74] != 8 ||
		sheng_pen_u32(p + 3948) != 981 ||
		sheng_pen_u32(p + 16) != ~0x505U ||
		sheng_pen_u32(p + 3956) != ~981U ||
		sheng_pen_u16(p + 12) != (sheng_pen_u16(p + 4) ^ 0xffff) ||
		sheng_pen_u16(p + 3952) != (sheng_pen_u16(p + 3944) ^ 0xffff) ||
		sheng_pen_checksum(p, 0x505) != sheng_pen_u16(p + 4) ||
		sheng_pen_checksum(p, 981) != sheng_pen_u16(p + 3944)) {
		state->have_sequence = 0;
		state->last_down_ns = 0;
		return 0;
	}
	sequence = sheng_pen_u16(p + 2);
	if (!state->have_sequence ||
		sequence != ((state->previous_sequence + 1) & 0xffff))
		state->last_down_ns = 0;
	state->previous_sequence = sequence;
	state->have_sequence = 1;
	pressure = sheng_pen_u16(p + 68);
	if (pressure == 16 && p[80] == 0) {
		state->last_down_ns = now_ns;
		return 0;
	}
	if (pressure != 0 || p[80] != 1 || !state->last_down_ns ||
		now_ns < state->last_down_ns ||
		now_ns - state->last_down_ns > hold_ms * 1000000ULL) {
		state->last_down_ns = 0;
		return 0;
	}
	sheng_pen_put16(p + 68, 16);
	p[80] = 0;
	checksum = sheng_pen_checksum(p, 981);
	sheng_pen_put16(p + 3944, checksum);
	sheng_pen_put16(p + 3952, checksum ^ 0xffff);
	checksum = sheng_pen_checksum(p, 0x505);
	sheng_pen_put16(p + 4, checksum);
	sheng_pen_put16(p + 12, checksum ^ 0xffff);
	return 1;
}
#endif
