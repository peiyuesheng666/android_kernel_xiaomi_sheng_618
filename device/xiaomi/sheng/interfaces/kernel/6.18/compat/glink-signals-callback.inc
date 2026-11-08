/* SPDX-License-Identifier: GPL-2.0-only */
bool sheng_rpmsg_supports_rx_done(struct rpmsg_endpoint *ept)
{
	return ept && ept->ops == &glink_endpoint_ops && to_glink_channel(ept)->rx_done;
}
EXPORT_SYMBOL_GPL(sheng_rpmsg_supports_rx_done);

int sheng_rpmsg_set_signals_callback(struct rpmsg_endpoint *ept, sheng_rpmsg_rx_sig_t callback)
{
	struct glink_channel *channel;
	unsigned long flags;

	if (!ept)
		return -EINVAL;
	if (ept->ops != &glink_endpoint_ops)
		return -ENXIO;
	channel = to_glink_channel(ept);
	spin_lock_irqsave(&channel->recv_lock, flags);
	channel->sig_cb = callback;
	spin_unlock_irqrestore(&channel->recv_lock, flags);
	return 0;
}
EXPORT_SYMBOL_GPL(sheng_rpmsg_set_signals_callback);
