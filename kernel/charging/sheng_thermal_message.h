/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Sheng's shipping mi_thermal_interface ABI, hosted by the charger on 6.18.
 * The stock module's 27 thermal_message and 2 power_save attributes are the
 * authority for names, modes, defaults and units. This does not calibrate or
 * replace mi_thermald's virtual sensor, thresholds, or charging policy.
 */
#ifndef SHENG_THERMAL_MESSAGE_H
#define SHENG_THERMAL_MESSAGE_H

#include <linux/cpufreq.h>
#include <linux/device.h>
#include <linux/list.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/pm_qos.h>
#include <linux/power_supply.h>
#include <linux/slab.h>
#include <linux/workqueue.h>

#define SHENG_TM_SCALARS(X) \
	X(temp_state, 0) X(sconfig, -1) X(balance_mode, 0) \
	X(modem_limit, 0) X(wifi_limit, 0) X(flash_state, 0) \
	X(torch_level, 0) X(torch_real_level, -1) X(thermal_max_brightness, 0) \
	X(voice_limit, 0) X(market_download_limit, 0) \
	X(board_sensor_temp_comp, 0) X(poor_modem_limit, 0) \
	X(cpu_nolimit_temp, 0) X(modem_rate, 0) X(modem_level, 0) \
	X(charger_temp, -1) X(powersave_mode, -1) X(power_level, -1)

struct sheng_thermal_qos {
	struct list_head node;
	struct cpufreq_policy *policy;
	struct freq_qos_request request;
};

struct sheng_thermal_message {
	struct device *message;
	struct device *power_save;
	struct mutex lock;
	struct list_head qos_requests;
	struct notifier_block cpufreq_nb;
	struct notifier_block usb_nb;
	struct work_struct usb_work;
	bool cpufreq_registered;
	bool usb_registered;
	bool stopping;
	void *data;
	int (*set_board_temp)(void *data, int deci_c);
	int (*get_usb_online)(void *data, int *online);
	struct power_supply *usb;
	atomic_t screen_state;
	atomic_t usb_online;
#define SHENG_TM_FIELD(name, initial) atomic_t name;
	SHENG_TM_SCALARS(SHENG_TM_FIELD)
#undef SHENG_TM_FIELD
	char board_sensor[128];
	char boost[128];
	char board_sensor_temp[128];
	char board_sensor_second_temp[128];
	char board_sensor_other_temp[128];
	char ambient_sensor_temp[128];
};

struct sheng_thermal_attribute {
	struct device_attribute dev_attr;
	size_t offset;
};

static ssize_t sheng_tm_scalar_show(struct device *dev,
		struct device_attribute *attr, char *buf)
{
	struct sheng_thermal_message *tm = dev_get_drvdata(dev);
	struct sheng_thermal_attribute *a = container_of(attr,
			struct sheng_thermal_attribute, dev_attr);
	atomic_t *value = (void *)tm + a->offset;

	return sysfs_emit(buf, "%d\n", atomic_read(value));
}

static ssize_t sheng_tm_scalar_store(struct device *dev,
		struct device_attribute *attr, const char *buf, size_t count)
{
	struct sheng_thermal_message *tm = dev_get_drvdata(dev);
	struct sheng_thermal_attribute *a = container_of(attr,
			struct sheng_thermal_attribute, dev_attr);
	atomic_t *value = (void *)tm + a->offset;
	int parsed, rc;

	if (READ_ONCE(tm->stopping))
		return -ENODEV;
	rc = kstrtoint(buf, 10, &parsed);
	if (rc)
		return rc;
	atomic_set(value, parsed);
	return count;
}

#define SHENG_TM_SCALAR_ATTR(name, initial) \
	static struct sheng_thermal_attribute sheng_tm_attr_##name = { \
		.dev_attr = __ATTR(name, 0664, sheng_tm_scalar_show, \
				sheng_tm_scalar_store), \
		.offset = offsetof(struct sheng_thermal_message, name), \
	};
SHENG_TM_SCALARS(SHENG_TM_SCALAR_ATTR)
#undef SHENG_TM_SCALAR_ATTR

static ssize_t sheng_tm_string_show(struct device *dev,
		struct device_attribute *attr, char *buf)
{
	struct sheng_thermal_message *tm = dev_get_drvdata(dev);
	struct sheng_thermal_attribute *a = container_of(attr,
			struct sheng_thermal_attribute, dev_attr);
	ssize_t rc;

	mutex_lock(&tm->lock);
	rc = sysfs_emit(buf, "%s", (char *)tm + a->offset);
	mutex_unlock(&tm->lock);
	return rc;
}

static void sheng_tm_copy_string(char *dest, const char *buf, size_t count)
{
	size_t length = min_t(size_t, count, 127);

	/* Stock has a 128-byte buffer. Treat its contents as data, not a format. */
	memcpy(dest, buf, length);
	dest[length] = '\0';
}

static ssize_t sheng_tm_string_store(struct device *dev,
		struct device_attribute *attr, const char *buf, size_t count)
{
	struct sheng_thermal_message *tm = dev_get_drvdata(dev);
	struct sheng_thermal_attribute *a = container_of(attr,
			struct sheng_thermal_attribute, dev_attr);
	ssize_t rc = count;

	mutex_lock(&tm->lock);
	if (tm->stopping)
		rc = -ENODEV;
	else
		sheng_tm_copy_string((char *)tm + a->offset, buf, count);
	mutex_unlock(&tm->lock);
	return rc;
}

static ssize_t sheng_tm_board_temp_store(struct device *dev,
		struct device_attribute *attr, const char *buf, size_t count)
{
	struct sheng_thermal_message *tm = dev_get_drvdata(dev);
	int milli_c, rc;

	rc = kstrtoint(buf, 10, &milli_c);
	if (rc)
		return rc;
	mutex_lock(&tm->lock);
	/* Shipping ARM64 code uses signed division by 100: mC -> 0.1 C. */
	rc = tm->stopping ? -ENODEV : tm->set_board_temp(tm->data, milli_c / 100);
	if (!rc)
		sheng_tm_copy_string(tm->board_sensor_temp, buf, count);
	mutex_unlock(&tm->lock);
	return rc < 0 ? rc : count;
}

#define SHENG_TM_STRING_ATTR(name, mode, store_fn) \
	static struct sheng_thermal_attribute sheng_tm_attr_##name = { \
		.dev_attr = __ATTR(name, mode, sheng_tm_string_show, store_fn), \
		.offset = offsetof(struct sheng_thermal_message, name), \
	};
SHENG_TM_STRING_ATTR(boost, 0644, sheng_tm_string_store)
SHENG_TM_STRING_ATTR(board_sensor, 0664, NULL)
SHENG_TM_STRING_ATTR(board_sensor_temp, 0664, sheng_tm_board_temp_store)
SHENG_TM_STRING_ATTR(board_sensor_second_temp, 0664, sheng_tm_string_store)
SHENG_TM_STRING_ATTR(board_sensor_other_temp, 0664, sheng_tm_string_store)
SHENG_TM_STRING_ATTR(ambient_sensor_temp, 0664, sheng_tm_string_store)
#undef SHENG_TM_STRING_ATTR

static ssize_t sheng_tm_ambient_show(struct device *dev,
		struct device_attribute *attr, char *buf)
{
	return sysfs_emit(buf, "ABT-SENSOR");
}

static struct device_attribute sheng_tm_attr_ambient_sensor =
	__ATTR(ambient_sensor, 0664, sheng_tm_ambient_show, NULL);

static struct sheng_thermal_attribute sheng_tm_attr_screen_state = {
	.dev_attr = __ATTR(screen_state, 0664, sheng_tm_scalar_show, NULL),
	.offset = offsetof(struct sheng_thermal_message, screen_state),
};
static struct sheng_thermal_attribute sheng_tm_attr_usb_online = {
	.dev_attr = __ATTR(usb_online, 0664, sheng_tm_scalar_show, NULL),
	.offset = offsetof(struct sheng_thermal_message, usb_online),
};

/* Match stock: select the greatest table frequency no higher than the request.
 * A request below the lowest entry leaves the previous vote unchanged. */
static unsigned int sheng_tm_max_frequency(struct cpufreq_policy *policy,
		unsigned int requested)
{
	struct cpufreq_frequency_table *entry;
	unsigned int selected = 0;

	cpufreq_for_each_valid_entry(entry, policy->freq_table) {
		if (entry->frequency <= requested && entry->frequency > selected)
			selected = entry->frequency;
	}
	return selected;
}

static int sheng_tm_cpu_limit(struct sheng_thermal_message *tm,
		unsigned int cpu, unsigned int maximum)
{
	struct cpufreq_policy *policy;
	struct sheng_thermal_qos *qos;
	unsigned int selected;
	int rc = 0;

	if (cpu >= nr_cpu_ids || !cpu_possible(cpu))
		return -EINVAL;
	policy = cpufreq_cpu_get(cpu);
	if (!policy)
		return -EAGAIN;
	/* Keep policy -> interface lock order, including policy removal. */
	down_read(&policy->rwsem);
	mutex_lock(&tm->lock);
	if (tm->stopping || cpumask_empty(policy->cpus) || !policy->freq_table) {
		rc = -ENODEV;
		goto out;
	}
	selected = sheng_tm_max_frequency(policy, maximum);
	if (!selected)
		goto out;
	list_for_each_entry(qos, &tm->qos_requests, node) {
		if (qos->policy == policy) {
			rc = freq_qos_update_request(&qos->request, selected);
			goto out;
		}
	}
	qos = kzalloc(sizeof(*qos), GFP_KERNEL);
	if (!qos) {
		rc = -ENOMEM;
		goto out;
	}
	qos->policy = policy;
	rc = freq_qos_add_request(&policy->constraints, &qos->request,
			FREQ_QOS_MAX, selected);
	if (rc < 0)
		kfree(qos);
	else
		list_add_tail(&qos->node, &tm->qos_requests);
out:
	mutex_unlock(&tm->lock);
	up_read(&policy->rwsem);
	cpufreq_cpu_put(policy);
	return rc < 0 ? rc : 0;
}

static int sheng_tm_policy_notify(struct notifier_block *nb,
		unsigned long event, void *data)
{
	struct sheng_thermal_message *tm = container_of(nb,
			struct sheng_thermal_message, cpufreq_nb);
	struct sheng_thermal_qos *qos, *next;

	if (event != CPUFREQ_REMOVE_POLICY)
		return NOTIFY_DONE;
	/* No persistent cpufreq reference: release votes before the policy is freed. */
	mutex_lock(&tm->lock);
	list_for_each_entry_safe(qos, next, &tm->qos_requests, node) {
		if (qos->policy == data) {
			freq_qos_remove_request(&qos->request);
			list_del(&qos->node);
			kfree(qos);
		}
	}
	mutex_unlock(&tm->lock);
	return NOTIFY_OK;
}

static ssize_t sheng_tm_cpu_limits_show(struct device *dev,
		struct device_attribute *attr, char *buf)
{
	return 0;
}

static ssize_t sheng_tm_cpu_limits_store(struct device *dev,
		struct device_attribute *attr, const char *buf, size_t count)
{
	struct sheng_thermal_message *tm = dev_get_drvdata(dev);
	unsigned int cpu, maximum;
	char extra;
	int rc;

	if (sscanf(buf, "cpu%u %u %c", &cpu, &maximum, &extra) != 2)
		return -EINVAL;
	rc = sheng_tm_cpu_limit(tm, cpu, maximum);
	return rc < 0 ? rc : count;
}

static struct device_attribute sheng_tm_attr_cpu_limits =
	__ATTR(cpu_limits, 0664, sheng_tm_cpu_limits_show, sheng_tm_cpu_limits_store);

#define SHENG_TM_ATTR(name) &sheng_tm_attr_##name.dev_attr.attr
static struct attribute *sheng_tm_attrs[] = {
	SHENG_TM_ATTR(temp_state), &sheng_tm_attr_cpu_limits.attr,
	SHENG_TM_ATTR(sconfig), SHENG_TM_ATTR(screen_state), SHENG_TM_ATTR(boost),
	SHENG_TM_ATTR(board_sensor), SHENG_TM_ATTR(board_sensor_temp),
	SHENG_TM_ATTR(board_sensor_second_temp), SHENG_TM_ATTR(board_sensor_other_temp),
	SHENG_TM_ATTR(balance_mode), SHENG_TM_ATTR(modem_limit), SHENG_TM_ATTR(wifi_limit),
	SHENG_TM_ATTR(flash_state), SHENG_TM_ATTR(torch_level), SHENG_TM_ATTR(torch_real_level),
	SHENG_TM_ATTR(thermal_max_brightness), SHENG_TM_ATTR(voice_limit),
	SHENG_TM_ATTR(market_download_limit), SHENG_TM_ATTR(board_sensor_temp_comp),
	SHENG_TM_ATTR(poor_modem_limit), SHENG_TM_ATTR(cpu_nolimit_temp),
	SHENG_TM_ATTR(modem_rate), SHENG_TM_ATTR(modem_level),
	&sheng_tm_attr_ambient_sensor.attr, SHENG_TM_ATTR(ambient_sensor_temp),
	SHENG_TM_ATTR(charger_temp), SHENG_TM_ATTR(usb_online), NULL,
};
ATTRIBUTE_GROUPS(sheng_tm);

static struct attribute *sheng_power_save_attrs[] = {
	SHENG_TM_ATTR(powersave_mode), SHENG_TM_ATTR(power_level), NULL,
};
ATTRIBUTE_GROUPS(sheng_power_save);
#undef SHENG_TM_ATTR

static void sheng_tm_usb_work(struct work_struct *work)
{
	struct sheng_thermal_message *tm = container_of(work,
			struct sheng_thermal_message, usb_work);
	int online;

	if (READ_ONCE(tm->stopping) || tm->get_usb_online(tm->data, &online))
		return;
	atomic_set(&tm->usb_online, online);
	/* Stock notifies after each successful USB supply update, even if unchanged. */
	sysfs_notify(&tm->message->kobj, NULL, "usb_online");
}

static int sheng_tm_usb_notify(struct notifier_block *nb,
		unsigned long event, void *data)
{
	struct sheng_thermal_message *tm = container_of(nb,
			struct sheng_thermal_message, usb_nb);

	if (event == PSY_EVENT_PROP_CHANGED && data == tm->usb &&
	    !READ_ONCE(tm->stopping))
		schedule_work(&tm->usb_work);
	return NOTIFY_OK;
}

/* Called only for completed (not early) events from the actual primary panel.
 * The owner stops its panel callback before unregistering this interface. */
static void sheng_thermal_screen_changed(struct sheng_thermal_message *tm, bool on)
{
	if (tm && !READ_ONCE(tm->stopping) && atomic_xchg(&tm->screen_state, on) != on)
		sysfs_notify(&tm->message->kobj, NULL, "screen_state");
}

static void sheng_thermal_message_unregister(struct sheng_thermal_message *tm)
{
	struct sheng_thermal_qos *qos, *next;

	if (!tm)
		return;
	WRITE_ONCE(tm->stopping, true);
	if (tm->usb_registered)
		power_supply_unreg_notifier(&tm->usb_nb);
	cancel_work_sync(&tm->usb_work);
	/* device_unregister drains active sysfs callbacks before returning. */
	if (tm->power_save)
		device_unregister(tm->power_save);
	if (tm->message)
		device_unregister(tm->message);
	if (tm->cpufreq_registered)
		cpufreq_unregister_notifier(&tm->cpufreq_nb, CPUFREQ_POLICY_NOTIFIER);
	mutex_lock(&tm->lock);
	list_for_each_entry_safe(qos, next, &tm->qos_requests, node) {
		freq_qos_remove_request(&qos->request);
		list_del(&qos->node);
		kfree(qos);
	}
	mutex_unlock(&tm->lock);
	kfree(tm);
}

static struct sheng_thermal_message *sheng_thermal_message_register(
		const struct class *thermal_class, struct power_supply *usb, void *data,
		int (*set_board_temp)(void *, int), int (*get_usb_online)(void *, int *))
{
	struct sheng_thermal_message *tm;
	struct device_node *node;
	const char *sensor = "invalid";
	int rc;

	if (!thermal_class || !usb || !set_board_temp || !get_usb_online)
		return ERR_PTR(-EINVAL);
	tm = kzalloc(sizeof(*tm), GFP_KERNEL);
	if (!tm)
		return ERR_PTR(-ENOMEM);
	mutex_init(&tm->lock);
	INIT_LIST_HEAD(&tm->qos_requests);
	INIT_WORK(&tm->usb_work, sheng_tm_usb_work);
	tm->data = data;
	tm->usb = usb;
	tm->set_board_temp = set_board_temp;
	tm->get_usb_online = get_usb_online;
#define SHENG_TM_INIT(name, initial) atomic_set(&tm->name, initial);
	SHENG_TM_SCALARS(SHENG_TM_INIT)
#undef SHENG_TM_INIT
	atomic_set(&tm->screen_state, 0);
	atomic_set(&tm->usb_online, 0);
	node = of_find_node_by_name(NULL, "thermal-message");
	if (node)
		of_property_read_string(node, "board-sensor", &sensor);
	rc = strscpy(tm->board_sensor, sensor, sizeof(tm->board_sensor));
	of_node_put(node);
	if (rc < 0)
		goto error;
	tm->cpufreq_nb.notifier_call = sheng_tm_policy_notify;
	rc = cpufreq_register_notifier(&tm->cpufreq_nb, CPUFREQ_POLICY_NOTIFIER);
	if (rc)
		goto error;
	tm->cpufreq_registered = true;
	/* Borrow the cooling device's public class, never private kernfs layouts. */
	tm->message = device_create_with_groups(thermal_class, NULL, 0, tm,
			sheng_tm_groups, "thermal_message");
	if (IS_ERR(tm->message)) {
		rc = PTR_ERR(tm->message);
		tm->message = NULL;
		goto error;
	}
	tm->power_save = device_create_with_groups(thermal_class, NULL, 0, tm,
			sheng_power_save_groups, "power_save");
	if (IS_ERR(tm->power_save)) {
		rc = PTR_ERR(tm->power_save);
		tm->power_save = NULL;
		goto error;
	}
	tm->usb_nb.notifier_call = sheng_tm_usb_notify;
	rc = power_supply_reg_notifier(&tm->usb_nb);
	if (rc)
		goto error;
	tm->usb_registered = true;
	schedule_work(&tm->usb_work);
	return tm;
error:
	sheng_thermal_message_unregister(tm);
	return ERR_PTR(rc);
}

#undef SHENG_TM_SCALARS
#endif
