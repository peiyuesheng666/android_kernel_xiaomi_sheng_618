/* SPDX-License-Identifier: GPL-2.0-only */
/* Replaces reference probe/PM code; uses the original sheng DT unchanged. */
static void sheng_nano_firmware_worker(struct work_struct *work)
{
	struct nanosic_wn8030 *nano =
		container_of(work, struct nanosic_wn8030, fw_worker.work);
	int ret;

	mutex_lock(&nano->io_lock);
	if (nano->removing) {
		mutex_unlock(&nano->io_lock);
		return;
	}
	nano->fw_attempts++;
	/* Firmware is volatile; resetting the MCU does not flash its storage. */
	gpiod_set_value_cansleep(nano->reset_gpio, 1);
	msleep(10);
	gpiod_set_value_cansleep(nano->sleep_gpio, 0);
	gpiod_set_value_cansleep(nano->reset_gpio, 0);
	msleep(20);
	ret = nanosic_wn8030_check_boot_id(nano);
	if (!ret) {
		ret = nanosic_wn8030_get_boot_state(nano);
		if (ret > 0)
			ret = -EINVAL;
	}
	if (!ret)
		ret = nanosic_wn8030_load_fw(nano);
	if (!ret) {
		nano->suspended = false;
		nano->ready = true;
		enable_irq(nano->client->irq);
		dev_info(nano->dev, "sheng_nanosic MCU RAM firmware ready, attempt=%u\n",
			 nano->fw_attempts);
	} else if (ret == -ENOENT && nano->fw_attempts < 60) {
		/* Same stock /odm mount race as the touch firmware. */
		schedule_delayed_work(&nano->fw_worker, HZ);
	} else {
		dev_err(nano->dev, "sheng_nanosic MCU firmware failed: %d attempt=%u\n",
			ret, nano->fw_attempts);
	}
	mutex_unlock(&nano->io_lock);
}

static int nanosic_wn8030_probe(struct i2c_client *client)
{
	struct nanosic_wn8030 *nano;
	struct device *dev = &client->dev;
	struct gpio_desc *irq_gpio;
	const char *model;
	int ret, i;

	if (of_property_read_string(of_root, "model", &model) ||
	    strcmp(model, "Qualcomm Technologies, Inc. 8550 sheng"))
		return -ENODEV;
	nano = kzalloc(sizeof(*nano), GFP_KERNEL);
	if (!nano)
		return -ENOMEM;
	nano->dev = dev;
	nano->client = client;
	kref_init(&nano->refs);
	mutex_init(&nano->io_lock);
	mutex_init(&nano->conn_mutex);
	mutex_init(&nano->clients_lock);
	INIT_LIST_HEAD(&nano->clients);
	INIT_DELAYED_WORK(&nano->wake_worker, nanosic_wn8030_wake_worker);
	INIT_DELAYED_WORK(&nano->fw_worker, sheng_nano_firmware_worker);

	/* Reference DTS confirms reset and sleep are physically active-low. */
	nano->reset_gpio = sheng_nano_gpio(dev, "reset_pin", GPIOF_OUT_INIT_HIGH, true);
	if (IS_ERR(nano->reset_gpio)) {
		ret = PTR_ERR(nano->reset_gpio);
		goto free;
	}
	nano->sleep_gpio = sheng_nano_gpio(dev, "sleep_pin", GPIOF_OUT_INIT_HIGH, true);
	if (IS_ERR(nano->sleep_gpio)) {
		ret = PTR_ERR(nano->sleep_gpio);
		goto free;
	}
	nano->status_gpio = sheng_nano_gpio(dev, "status_pin", GPIOF_IN, false);
	if (IS_ERR(nano->status_gpio)) {
		ret = PTR_ERR(nano->status_gpio);
		goto free;
	}
	irq_gpio = sheng_nano_gpio(dev, "irq_pin", GPIOF_IN, false);
	if (IS_ERR(irq_gpio)) {
		ret = PTR_ERR(irq_gpio);
		goto free;
	}
	client->irq = gpiod_to_irq(irq_gpio);
	if (client->irq < 0) {
		ret = client->irq;
		goto free;
	}
	for (i = 0; i < ARRAY_SIZE(nano->supplies); i++)
		nano->supplies[i].supply = nanosic_wn8030_supply_names[i];
	ret = devm_regulator_bulk_get(dev, ARRAY_SIZE(nano->supplies), nano->supplies);
	if (ret)
		goto free;
	nano->regmap = devm_regmap_init_i2c(client, &nanosic_wn8030_regmap_config);
	if (IS_ERR(nano->regmap)) {
		ret = PTR_ERR(nano->regmap);
		goto free;
	}
	ret = nanosic_wn8030_power_on(nano);
	if (ret)
		goto free;
	i2c_set_clientdata(client, nano);
	ret = devm_request_threaded_irq(dev, client->irq, NULL,
		nanosic_wn8030_handler, IRQF_ONESHOT | IRQF_TRIGGER_RISING |
		IRQF_NO_AUTOEN, "sheng_nanosic", nano);
	if (ret)
		goto power_off;
	nano->raw_misc.minor = MISC_DYNAMIC_MINOR;
	nano->raw_misc.name = "nanodev0";
	nano->raw_misc.fops = &sheng_nano_fops;
	nano->raw_misc.parent = dev;
	/* Stock init assigns system ownership/mode on boot. */
	ret = misc_register(&nano->raw_misc);
	if (ret)
		goto free_irq;
	dev_info(dev, "sheng_nanosic registered stock nanodev0 transport irq=%d\n", client->irq);
	schedule_delayed_work(&nano->fw_worker, HZ);
	return 0;

free_irq:
	devm_free_irq(dev, client->irq, nano);
power_off:
	nanosic_wn8030_power_off(nano);
free:
	dev_err_probe(dev, ret, "sheng_nanosic probe failed\n");
	kref_put(&nano->refs, sheng_nano_free);
	return ret;
}

static void nanosic_wn8030_remove(struct i2c_client *client)
{
	struct nanosic_wn8030 *nano = i2c_get_clientdata(client);
	bool ready;

	mutex_lock(&nano->io_lock);
	sheng_nano_disconnect_clients(nano);
	ready = nano->ready;
	nano->ready = false;
	mutex_unlock(&nano->io_lock);
	misc_deregister(&nano->raw_misc);
	cancel_delayed_work_sync(&nano->fw_worker);
	if (ready && !nano->suspended)
		disable_irq(client->irq);
	devm_free_irq(&client->dev, client->irq, nano);
	cancel_delayed_work_sync(&nano->wake_worker);
	if (nano->hid_keyboard)
		hid_destroy_device(nano->hid_keyboard);
	if (nano->hid_touchpad)
		hid_destroy_device(nano->hid_touchpad);
	nanosic_wn8030_power_off(nano);
	kref_put(&nano->refs, sheng_nano_free);
}

static int nanosic_wn8030_suspend(struct device *dev)
{
	struct nanosic_wn8030 *nano = dev_get_drvdata(dev);

	cancel_delayed_work_sync(&nano->fw_worker);
	if (nano->ready)
		disable_irq(nano->client->irq);
	cancel_delayed_work_sync(&nano->wake_worker);
	mutex_lock(&nano->io_lock);
	nano->suspended = true;
	gpiod_set_value_cansleep(nano->sleep_gpio, 1);
	mutex_unlock(&nano->io_lock);
	return 0;
}

static int nanosic_wn8030_resume(struct device *dev)
{
	struct nanosic_wn8030 *nano = dev_get_drvdata(dev);

	if (!nano->ready) {
		nano->fw_attempts = 0;
		schedule_delayed_work(&nano->fw_worker, 0);
		return 0;
	}
	enable_irq(nano->client->irq);
	mutex_lock(&nano->io_lock);
	gpiod_set_value_cansleep(nano->sleep_gpio, 0);
	mutex_unlock(&nano->io_lock);
	msleep(25);
	if (READ_ONCE(nano->suspended)) {
		disable_irq(nano->client->irq);
		mutex_lock(&nano->io_lock);
		nano->ready = false;
		nano->fw_attempts = 0;
		mutex_unlock(&nano->io_lock);
		schedule_delayed_work(&nano->fw_worker, 0);
	} else {
		mutex_lock(&nano->io_lock);
		nanosic_wn8030_set_kb_power(nano, true);
		mutex_unlock(&nano->io_lock);
	}
	return 0;
}

static DEFINE_SIMPLE_DEV_PM_OPS(nanosic_wn8030_pm_ops,
	nanosic_wn8030_suspend, nanosic_wn8030_resume);

static const struct of_device_id nanosic_wn8030_of_match[] = {
	{ .compatible = "nanosic,803" },
	{ }
};
MODULE_DEVICE_TABLE(of, nanosic_wn8030_of_match);

static struct i2c_driver nanosic_wn8030_driver = {
	.driver = {
		.name = "nanosic_driver",
		.of_match_table = nanosic_wn8030_of_match,
		.pm = pm_sleep_ptr(&nanosic_wn8030_pm_ops),
	},
	.probe = nanosic_wn8030_probe,
	.remove = nanosic_wn8030_remove,
};
module_i2c_driver(nanosic_wn8030_driver);
MODULE_AUTHOR("map220v <map220v300@gmail.com>");
MODULE_DESCRIPTION("Sheng WN8030 keyboard MCU with stock HyperOS transport");
MODULE_LICENSE("GPL v2");
