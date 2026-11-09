/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SHENG_EARLY_SCAN_TRACE_H
#define SHENG_EARLY_SCAN_TRACE_H
#include <linux/io.h>
#include <linux/of_address.h>
#include <linux/printk.h>
#include <linux/string.h>

/* Diagnostic snapshots at powered boot handoff sites, without clock votes,
 * status clears, panel commands or timing writes. Bases and block offsets
 * come from sheng's live DT. Register fields match the fixed Kalama drivers. */
static inline int sheng_early_scan_probe(const char *stage, bool dump, u32 *status)
{
	struct device_node *display, *clock;
	struct resource mdp_res, clock_res;
	void __iomem *mdp = NULL, *cc = NULL;
	const char *model;
	u32 intfs[4], pipes[10], top, ahb, core, gdsc, irq;
	int i, ret = -ENODEV;

	if (of_property_read_string(of_root, "model", &model) ||
	    strcmp(model, "Qualcomm Technologies, Inc. 8550 sheng"))
		return -ENODEV;
	display = of_find_compatible_node(NULL, NULL, "qcom,sde-kms");
	clock = of_find_compatible_node(NULL, NULL, "qcom,kalama-dispcc");
	if (!display || !clock ||
	    of_address_to_resource(display, 0, &mdp_res) ||
	    of_address_to_resource(clock, 0, &clock_res) ||
	    of_property_read_u32(display, "qcom,sde-off", &top) ||
	    of_property_read_u32_array(display, "qcom,sde-intf-off", intfs, 4) ||
	    of_property_read_u32_array(display, "qcom,sde-sspp-off", pipes, 10) ||
	    resource_size(&clock_res) < 0x9004 ||
	    (u64)top + 0x18 > resource_size(&mdp_res))
		goto out;
	for (i = 0; i < 4; i++)
		if ((u64)intfs[i] + 0x1c8 > resource_size(&mdp_res))
			goto out;
	for (i = 0; i < 10; i++)
		if ((u64)pipes[i] + 0x34 > resource_size(&mdp_res))
			goto out;
	cc = ioremap(clock_res.start, resource_size(&clock_res));
	if (!cc)
		goto out;
	ahb = readl_relaxed(cc + 0x80a4);
	core = readl_relaxed(cc + 0x800c);
	gdsc = readl_relaxed(cc + 0x9000);
	if (dump)
		pr_info("sheng early scan: %s power=%x ahb=%x core=%x\n",
			stage, gdsc, ahb, core);
	/* Never touch a visibly halted bus or unpowered display island. */
	if (!(gdsc & BIT(31)) || !(ahb & BIT(0)) || (ahb & BIT(31)) ||
	    !(core & BIT(0)) || (core & BIT(31))) {
		ret = -EAGAIN;
		goto out;
	}
	mdp = ioremap(mdp_res.start, resource_size(&mdp_res));
	if (!mdp)
		goto out;
	irq = readl_relaxed(mdp + top + 0x14);
	if (status)
		*status = irq;
	ret = 0;
	if (!dump)
		goto out;
	pr_info("sheng early scan: %s irq_en=%x irq_status=%x underrun=%x\n",
		stage, readl_relaxed(mdp + top + 0x10),
		irq, irq & (BIT(26) | BIT(28)));
	/* INTF_0=1; DT slots 1 and 2 are DSI, logged as intf2/intf3. */
	for (i = 1; i <= 2; i++)
		pr_info("sheng early scan: %s intf%d en=%x frame=%u line=%u status=%x\n",
			stage, i + 1, readl_relaxed(mdp + intfs[i]),
			readl_relaxed(mdp + intfs[i] + 0xac),
			readl_relaxed(mdp + intfs[i] + 0xb0) & 0xffff,
			readl_relaxed(mdp + intfs[i] + 0x1c4));
	for (i = 0; i < 10; i++) {
		u32 address = readl_relaxed(mdp + pipes[i] + 0x14);

		if (address)
			pr_info("sheng early scan: %s pipe%d off=%x addr=%x format=%x\n",
				stage, i, pipes[i], address,
				readl_relaxed(mdp + pipes[i] + 0x30));
	}
out:
	if (mdp)
		iounmap(mdp);
	if (cc)
		iounmap(cc);
	of_node_put(display);
	of_node_put(clock);
	return ret;
}

static inline void sheng_early_scan_trace(const char *stage)
{
	sheng_early_scan_probe(stage, true, NULL);
}
#endif
