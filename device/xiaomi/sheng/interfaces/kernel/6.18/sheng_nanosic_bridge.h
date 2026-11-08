/* SPDX-License-Identifier: GPL-2.0-only */
/* Stock HyperOS transport. Authentication messages are passed unchanged. */
#define SHENG_NANO_SLOTS 10

struct sheng_nano_packet {
	u8 len;
	u8 data[68];
};

struct sheng_nano_client {
	struct list_head link;
	struct nanosic_wn8030 *nano;
	struct mutex lock;
	wait_queue_head_t wait;
	u8 head, tail;
	struct sheng_nano_packet queue[SHENG_NANO_SLOTS];
};

static void sheng_nano_free(struct kref *ref)
{
	kfree(container_of(ref, struct nanosic_wn8030, refs));
}

static void sheng_nano_broadcast(struct nanosic_wn8030 *nano,
				 const u8 *buf, size_t len)
{
	struct sheng_nano_client *client;
	u8 next;

	if (!len || len > sizeof(client->queue[0].data))
		return;
	mutex_lock(&nano->clients_lock);
	list_for_each_entry(client, &nano->clients, link) {
		mutex_lock(&client->lock);
		next = (client->tail + 1) % SHENG_NANO_SLOTS;
		/* Match the stock bounded ring: drop new packets when full. */
		if (next != client->head) {
			client->queue[next].len = len;
			memcpy(client->queue[next].data, buf, len);
			WRITE_ONCE(client->tail, next);
			wake_up_interruptible(&client->wait);
		}
		mutex_unlock(&client->lock);
	}
	mutex_unlock(&nano->clients_lock);
}

static int sheng_nano_open(struct inode *inode, struct file *file)
{
	struct nanosic_wn8030 *nano =
		container_of(file->private_data, struct nanosic_wn8030, raw_misc);
	struct sheng_nano_client *client;

	client = kzalloc(sizeof(*client), GFP_KERNEL);
	if (!client)
		return -ENOMEM;
	client->nano = nano;
	mutex_init(&client->lock);
	init_waitqueue_head(&client->wait);
	mutex_lock(&nano->clients_lock);
	if (READ_ONCE(nano->removing)) {
		mutex_unlock(&nano->clients_lock);
		kfree(client);
		return -ENODEV;
	}
	kref_get(&nano->refs);
	list_add_tail(&client->link, &nano->clients);
	mutex_unlock(&nano->clients_lock);
	file->private_data = client;
	return nonseekable_open(inode, file);
}

static int sheng_nano_release(struct inode *inode, struct file *file)
{
	struct sheng_nano_client *client = file->private_data;
	struct nanosic_wn8030 *nano = client->nano;

	mutex_lock(&nano->clients_lock);
	list_del(&client->link);
	mutex_unlock(&nano->clients_lock);
	kfree(client);
	kref_put(&nano->refs, sheng_nano_free);
	return 0;
}

static ssize_t sheng_nano_read(struct file *file, char __user *buf,
			      size_t count, loff_t *pos)
{
	struct sheng_nano_client *client = file->private_data;
	struct sheng_nano_packet *packet;
	ssize_t ret;
	u8 next;

	if (!count)
		return 0;
	for (;;) {
		if (mutex_lock_interruptible(&client->lock))
			return -ERESTARTSYS;
		if (READ_ONCE(client->nano->removing)) {
			ret = -ENODEV;
			break;
		}
		if (client->head != client->tail) {
			next = (client->head + 1) % SHENG_NANO_SLOTS;
			packet = &client->queue[next];
			ret = min_t(size_t, count, packet->len);
			if (copy_to_user(buf, packet->data, ret))
				ret = -EFAULT;
			else
				WRITE_ONCE(client->head, next);
			break;
		}
		mutex_unlock(&client->lock);
		if (file->f_flags & O_NONBLOCK)
			return -EAGAIN;
		ret = wait_event_interruptible(client->wait,
			READ_ONCE(client->head) != READ_ONCE(client->tail) ||
			READ_ONCE(client->nano->removing));
		if (ret)
			return ret;
	}
	mutex_unlock(&client->lock);
	return ret;
}

static ssize_t sheng_nano_write(struct file *file, const char __user *buf,
			       size_t count, loff_t *pos)
{
	struct nanosic_wn8030 *nano =
		((struct sheng_nano_client *)file->private_data)->nano;
	u8 message[XM_WN8030_I2C_WRITE];
	int ret;

	if (count != sizeof(message))
		return -EINVAL;
	if (copy_from_user(message, buf, sizeof(message)))
		return -EFAULT;
	if (mutex_lock_interruptible(&nano->io_lock))
		return -ERESTARTSYS;
	if (READ_ONCE(nano->removing))
		ret = -ENODEV;
	else if (!nano->ready)
		ret = -EAGAIN;
	else if (nano->suspended)
		ret = -EHOSTDOWN;
	else
		ret = regmap_bulk_write(nano->regmap, 0x5c, message, sizeof(message));
	mutex_unlock(&nano->io_lock);
	return ret ? ret : count;
}

static __poll_t sheng_nano_poll(struct file *file, poll_table *wait)
{
	struct sheng_nano_client *client = file->private_data;
	__poll_t mask = 0;

	poll_wait(file, &client->wait, wait);
	if (READ_ONCE(client->nano->removing))
		return EPOLLHUP | EPOLLERR;
	if (READ_ONCE(client->head) != READ_ONCE(client->tail))
		mask |= EPOLLIN | EPOLLRDNORM;
	return mask;
}

static long sheng_nano_ioctl(struct file *file, unsigned int cmd,
			    unsigned long arg)
{
	/* Original poll/ioctl functions return ENOSYS; there is no token ioctl. */
	return -ENOSYS;
}

static const struct file_operations sheng_nano_fops = {
	.owner = THIS_MODULE,
	.open = sheng_nano_open,
	.release = sheng_nano_release,
	.read = sheng_nano_read,
	.write = sheng_nano_write,
	.poll = sheng_nano_poll,
	.unlocked_ioctl = sheng_nano_ioctl,
	.compat_ioctl = sheng_nano_ioctl,
};

static void sheng_nano_disconnect_clients(struct nanosic_wn8030 *nano)
{
	struct sheng_nano_client *client;

	mutex_lock(&nano->clients_lock);
	WRITE_ONCE(nano->removing, true);
	list_for_each_entry(client, &nano->clients, link)
		wake_up_interruptible(&client->wait);
	mutex_unlock(&nano->clients_lock);
}

/* Translate only property spelling and polarity; keep stock DT untouched. */
static struct gpio_desc *sheng_nano_gpio(struct device *dev, const char *name,
					unsigned long flags, bool active_low)
{
	int pin, ret;
	struct gpio_desc *desc;

	pin = of_get_named_gpio(dev->of_node, name, 0);
	if (pin < 0)
		return ERR_PTR(pin);
	ret = devm_gpio_request_one(dev, pin, flags, name);
	if (ret)
		return ERR_PTR(ret);
	desc = gpio_to_desc(pin);
	if (!desc)
		return ERR_PTR(-EINVAL);
	if (gpiod_is_active_low(desc) != active_low)
		gpiod_toggle_active_low(desc);
	return desc;
}
