/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SHENG_NANOSIC_POWER_H
#define SHENG_NANOSIC_POWER_H

/* Shipping Nanosic_regulator_init selects one digital rail at hwid 0x10000.
 * Newer sheng boards use dvdd-another (L12B), older boards use dvdd (L6B).
 * Read the bootloader's value; never enable both parallel digital supplies.
 */
static int sheng_nano_digital_supply_key(const char *bootargs, const char **key)
{
	static const char prefix[] = "hwid.hwid_value=";
	const char *value;
	char number[24];
	size_t len;
	u32 hwid;
	int ret;

	if (!bootargs || !key)
		return -EINVAL;
	value = bootargs;
	while ((value = strstr(value, prefix))) {
		if (value == bootargs || value[-1] == ' ' || value[-1] == '\t')
			break;
		value += sizeof(prefix) - 1;
	}
	if (!value)
		return -ENOENT;
	value += sizeof(prefix) - 1;
	len = strcspn(value, " \t\n");
	if (!len || len >= sizeof(number))
		return -EINVAL;
	memcpy(number, value, len);
	number[len] = '\0';
	ret = kstrtou32(number, 0, &hwid);
	if (ret)
		return ret;
	*key = hwid > 0x10000 ? "nanosic,dvdd-another-name" : "nanosic,dvdd-name";
	return 0;
}

#endif
