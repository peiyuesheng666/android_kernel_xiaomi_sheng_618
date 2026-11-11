// SPDX-License-Identifier: GPL-2.0-only
/*
 * HID driver for Nanosic WN8030 keyboard MCU
 *
 * Copyright (c) 2025 map220v <map220v300@gmail.com>
 */

#include <linux/gpio.h>
#include <linux/gpio/consumer.h>
#include <linux/of_gpio.h>
#include <linux/kref.h>
#include <linux/poll.h>
#include <linux/regulator/consumer.h>
#include <linux/uaccess.h>
#include <linux/unaligned.h>
#include <linux/delay.h>
#include <linux/firmware.h>
#include <linux/hid.h>
#include <linux/i2c.h>
#include <linux/interrupt.h>
#include <linux/kernel.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regmap.h>
#include <linux/workqueue.h>

#define WN8030_HEADER_ADDR 0x7FC0
#define WN8030_CODE_ADDR 0x8000

#define XM_WN8030_I2C_READ (68)
#define XM_WN8030_I2C_WRITE (66)

#define WN8030_NUM_SUPPLIES 2

struct nanosic_wn8030 {
	struct device *dev;
	struct i2c_client *client;
	struct hid_device *hid_keyboard;
	struct hid_device *hid_touchpad;

	struct gpio_desc *status_gpio;
	struct gpio_desc *sleep_gpio;
	struct gpio_desc *reset_gpio;
	struct regulator_bulk_data supplies[WN8030_NUM_SUPPLIES];

	struct regmap *regmap;
	struct mutex conn_mutex;
	struct delayed_work wake_worker;

	bool suspended;
	bool keyboard_attached;

	/* Stock HAL owns authentication; kernel only transports real messages. */
	struct miscdevice raw_misc;
	struct kref refs;
	struct mutex clients_lock;
	struct list_head clients;
	struct mutex io_lock;
	struct delayed_work fw_worker;
	unsigned int fw_attempts;
	struct delayed_work plugin_worker;
	int plugin_requested, plugin_sent;
	unsigned int plugin_retries;
	bool ready, removing;
	const struct firmware *ram_firmware;

};

#include "sheng_nanosic_bridge.h"
#include "sheng_nanosic_power.h"
#include "sheng_nanosic_connection.h"
#include "sheng_keyboard_charger.h"

static const struct regmap_config nanosic_wn8030_regmap_config = {
	.reg_bits = 8,
	.val_bits = 8,
};

#pragma pack(push, 1)
struct wn8030_bin_header {
	u8 flag[7];
	u16 chip_id;
	u32 ro_data;
	u32 rame_code; //??
	u32 rame_code_size; //??
	u32 code_entry;
	u16 pid;
	u16 vid;
	u8 major_version;
	u8 minor_version;
	char version_string[17];
	u32 ram_code_size;
	u32 ram_code_checksum;
	u32 unk;
	u8 device_type;
	u8 unk1[3];
};
#pragma pack(pop)

#pragma pack(push, 1)
struct wn8030_header_cmd {
	u8 cmd; /* 0x06 */
	u8 flag[7];
	u16 chip_id;
	u32 ram_code_source;
	u32 ram_code_dest;
	u32 ram_code_size;
	u32 code_entry;
	u16 pid;
	u16 vid;
	u8 major_version;
	u8 minor_version;
	u8 unk[17]; /* version_string? */
	u32 image_size;
	u32 ram_code_checksum;
	u32 image_checksum;
	u8 pad[3];
	u8 header_checksum;
};
#pragma pack(pop)

#pragma pack(push, 1)
struct wn8030_send_cmd {
	u8 cmd; /* 0x07 */
	__be32 ram_dest;
	__be32 size;
	u8 data[503];
};
#pragma pack(pop)

static u8 hid_keyboard_descriptor[] = {
	0x05, 0x01,        // Usage Page (Generic Desktop Ctrls)
	0x09, 0x06,        // Usage (Keyboard)
	0xA1, 0x01,        // Collection (Application)
	0x85, 0x05,        //   Report ID (5)
	0x05, 0x07,        //   Usage Page (Kbrd/Keypad)
	0x19, 0xE0,        //   Usage Minimum (0xE0)
	0x29, 0xE7,        //   Usage Maximum (0xE7)
	0x15, 0x00,        //   Logical Minimum (0)
	0x25, 0x01,        //   Logical Maximum (1)
	0x75, 0x01,        //   Report Size (1)
	0x95, 0x08,        //   Report Count (8)
	0x81, 0x02,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x81, 0x03,        //   Input (Const,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x95, 0x05,        //   Report Count (5)
	0x05, 0x08,        //   Usage Page (LEDs)
	0x19, 0x02,        //   Usage Minimum (Caps Lock)
	0x29, 0x02,        //   Usage Maximum (Caps Lock)
	0x91, 0x02,        //   Output (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position,Non-volatile)
	0x95, 0x01,        //   Report Count (1)
	0x75, 0x03,        //   Report Size (3)
	0x91, 0x01,        //   Output (Const,Array,Abs,No Wrap,Linear,Preferred State,No Null Position,Non-volatile)
	0x95, 0x06,        //   Report Count (6)
	0x75, 0x08,        //   Report Size (8)
	0x15, 0x00,        //   Logical Minimum (0)
	0x26, 0xA4, 0x00,  //   Logical Maximum (164)
	0x05, 0x07,        //   Usage Page (Kbrd/Keypad)
	0x19, 0x00,        //   Usage Minimum (0x00)
	0x2A, 0xA4, 0x00,  //   Usage Maximum (0xA4)
	0x81, 0x00,        //   Input (Data,Array,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0xC0,              // End Collection
	/* Stock HID_ConsumerReportDescriptor, report ID 0x06. */
	0x05, 0x0c, 0x09, 0x01, 0xa1, 0x01, 0x85, 0x06, 0x15, 0x00, 0x26, 0x80, 0x03, 0x19, 0x00, 0x2a, 0x80, 0x03, 0x75, 0x10, 0x95, 0x01, 0x81, 0x00, 0xc0,

};

static u8 hid_touchpad_descriptor[] = {
	0x05, 0x0D,        // Usage Page (Digitizer)
	0x09, 0x05,        // Usage (Touch Pad)
	0xA1, 0x01,        // Collection (Application)
	0x85, 0x19,        //   Report ID (25)
	0x15, 0x00,        //   Logical Minimum (0)
	0x25, 0x01,        //   Logical Maximum (1)
	0x35, 0x00,        //   Physical Minimum (0)
	0x45, 0x01,        //   Physical Maximum (1)
	0x75, 0x01,        //   Report Size (1)
	0x95, 0x02,        //   Report Count (2)
	0x05, 0x09,        //   Usage Page (Button)
	0x09, 0x01,        //   Usage (0x01)
	0x09, 0x02,        //   Usage (0x02)
	0x81, 0x02,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x95, 0x06,        //   Report Count (6)
	0x81, 0x01,        //   Input (Const,Array,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x05, 0x0D,        //   Usage Page (Digitizer)
	0x09, 0x22,        //   Usage (Finger)
	0xA1, 0x02,        //   Collection (Logical)
	0x09, 0x42,        //     Usage (Tip Switch)
	0x15, 0x00,        //     Logical Minimum (0)
	0x25, 0x01,        //     Logical Maximum (1)
	0x75, 0x01,        //     Report Size (1)
	0x95, 0x01,        //     Report Count (1)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x09, 0x32,        //     Usage (In Range)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x09, 0x47,        //     Usage (0x47)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x95, 0x05,        //     Report Count (5)
	0x81, 0x03,        //     Input (Const,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x75, 0x08,        //     Report Size (8)
	0x09, 0x51,        //     Usage (0x51)
	0x95, 0x01,        //     Report Count (1)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x05, 0x01,        //     Usage Page (Generic Desktop Ctrls)
	0x15, 0x00,        //     Logical Minimum (0)
	0x26, 0xE7, 0x0B,  //     Logical Maximum (3047)
	0x75, 0x10,        //     Report Size (16)
	0x55, 0x0D,        //     Unit Exponent (-3)
	0x65, 0x13,        //     Unit (System: English Linear, Length: Centimeter)
	0x09, 0x30,        //     Usage (X)
	0x35, 0x00,        //     Physical Minimum (0)
	0x46, 0x00, 0x00,  //     Physical Maximum (0)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x09, 0x31,        //     Usage (Y)
	0x26, 0xEF, 0x07,  //     Logical Maximum (2031)
	0x46, 0x00, 0x00,  //     Physical Maximum (0)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0xC0,              //   End Collection
	0xA1, 0x02,        //   Collection (Logical)
	0x05, 0x0D,        //     Usage Page (Digitizer)
	0x09, 0x42,        //     Usage (Tip Switch)
	0x15, 0x00,        //     Logical Minimum (0)
	0x25, 0x01,        //     Logical Maximum (1)
	0x75, 0x01,        //     Report Size (1)
	0x95, 0x01,        //     Report Count (1)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x09, 0x32,        //     Usage (In Range)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x09, 0x47,        //     Usage (0x47)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x95, 0x05,        //     Report Count (5)
	0x81, 0x03,        //     Input (Const,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x75, 0x08,        //     Report Size (8)
	0x09, 0x51,        //     Usage (0x51)
	0x95, 0x01,        //     Report Count (1)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x05, 0x01,        //     Usage Page (Generic Desktop Ctrls)
	0x15, 0x00,        //     Logical Minimum (0)
	0x26, 0xE7, 0x0B,  //     Logical Maximum (3047)
	0x75, 0x10,        //     Report Size (16)
	0x55, 0x0D,        //     Unit Exponent (-3)
	0x65, 0x13,        //     Unit (System: English Linear, Length: Centimeter)
	0x09, 0x30,        //     Usage (X)
	0x35, 0x00,        //     Physical Minimum (0)
	0x46, 0x00, 0x00,  //     Physical Maximum (0)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x09, 0x31,        //     Usage (Y)
	0x26, 0xEF, 0x07,  //     Logical Maximum (2031)
	0x46, 0x00, 0x00,  //     Physical Maximum (0)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0xC0,              //   End Collection
	0xA1, 0x02,        //   Collection (Logical)
	0x05, 0x0D,        //     Usage Page (Digitizer)
	0x09, 0x42,        //     Usage (Tip Switch)
	0x15, 0x00,        //     Logical Minimum (0)
	0x25, 0x01,        //     Logical Maximum (1)
	0x75, 0x01,        //     Report Size (1)
	0x95, 0x01,        //     Report Count (1)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x09, 0x32,        //     Usage (In Range)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x09, 0x47,        //     Usage (0x47)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x95, 0x05,        //     Report Count (5)
	0x81, 0x03,        //     Input (Const,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x75, 0x08,        //     Report Size (8)
	0x09, 0x51,        //     Usage (0x51)
	0x95, 0x01,        //     Report Count (1)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x05, 0x01,        //     Usage Page (Generic Desktop Ctrls)
	0x15, 0x00,        //     Logical Minimum (0)
	0x26, 0xE7, 0x0B,  //     Logical Maximum (3047)
	0x75, 0x10,        //     Report Size (16)
	0x55, 0x0D,        //     Unit Exponent (-3)
	0x65, 0x13,        //     Unit (System: English Linear, Length: Centimeter)
	0x09, 0x30,        //     Usage (X)
	0x35, 0x00,        //     Physical Minimum (0)
	0x46, 0x00, 0x00,  //     Physical Maximum (0)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x09, 0x31,        //     Usage (Y)
	0x26, 0xEF, 0x07,  //     Logical Maximum (2031)
	0x46, 0x00, 0x00,  //     Physical Maximum (0)
	0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0xC0,              //   End Collection
	0x05, 0x0D,        //   Usage Page (Digitizer)
	0x09, 0x54,        //   Usage (0x54)
	0x95, 0x01,        //   Report Count (1)
	0x75, 0x08,        //   Report Size (8)
	0x15, 0x00,        //   Logical Minimum (0)
	0x25, 0x08,        //   Logical Maximum (8)
	0x81, 0x02,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
	0x09, 0x55,        //   Usage (0x55)
	0xB1, 0x02,        //   Feature (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position,Non-volatile)
	0x06, 0x00, 0xFF,  //   Usage Page (Vendor Defined 0xFF00)
	0x09, 0xC5,        //   Usage (0xC5)
	0x15, 0x00,        //   Logical Minimum (0)
	0x26, 0xFF, 0x00,  //   Logical Maximum (255)
	0x75, 0x08,        //   Report Size (8)
	0x96, 0x00, 0x01,  //   Report Count (256)
	0xB1, 0x02,        //   Feature (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position,Non-volatile)
	0xC0,              // End Collection
};

static int nanosic_wn8030_hid_parse(struct hid_device *hid)
{
	if (hid->product == 0x00A3)
		return hid_parse_report(hid, hid_keyboard_descriptor, sizeof(hid_keyboard_descriptor));
	else if (hid->product == 0x00A1)
		return hid_parse_report(hid, hid_touchpad_descriptor, sizeof(hid_touchpad_descriptor));
	else
		return -ENODEV;
}

static int nanosic_wn8030_hid_start(struct hid_device *hid)
{
	return 0;
}

static void nanosic_wn8030_hid_stop(struct hid_device *hid)
{
	hid->claimed = 0;
}

static int nanosic_wn8030_hid_open(struct hid_device *hid)
{
	return 0;
}

static void nanosic_wn8030_hid_close(struct hid_device *hid)
{
}

static int nanosic_wn8030_raw_request(struct hid_device *hid,
				      unsigned char reportnum,
				      __u8 *buf, size_t len,
				      unsigned char rtype, int reqtype)
{
	return len;
}

static inline u32 nanosic_wn8030_checksum32(const u8 *data, int size)
{
	u32 checksum = 0;

	for (u32 i = 0; i < size; i += 4)
		checksum += get_unaligned_le32(data + i);

	return checksum;
}

static inline u8 nanosic_wn8030_checksum8(const u8 *data, int size)
{
	u8 checksum = 0;

	for (u32 i = 0; i < size; i++)
		checksum += data[i];

	return checksum;
}

static int nanosic_wn8030_set_caps_led(struct nanosic_wn8030 *nanosic, bool enable)
{
	u8 buf[XM_WN8030_I2C_WRITE] = { 0x32, 0x00, 0x4E, 0x31,
					0x80, 0x38, 0x2E, 0x01 };

	buf[8] = enable ? 0xFD : 0xFC;
	buf[9] = nanosic_wn8030_checksum8(&buf[2], 7);

	return regmap_bulk_write(nanosic->regmap, 0x5c, buf, sizeof(buf));
}

static int nanosic_wn8030_set_touchpad(struct nanosic_wn8030 *nanosic, bool enable)
{
	u8 buf[XM_WN8030_I2C_WRITE] = { 0x32, 0x00, 0x4E, 0x31,
					0x80, 0x38, 0x21, 0x01 };

	buf[8] = enable;
	buf[9] = nanosic_wn8030_checksum8(&buf[2], 7);

	return regmap_bulk_write(nanosic->regmap, 0x5c, buf, sizeof(buf));
}

static int nanosic_wn8030_set_kb_power(struct nanosic_wn8030 *nanosic, bool enable)
{
	u8 buf[XM_WN8030_I2C_WRITE] = { 0x32, 0x00, 0x4E, 0x31,
					0x80, 0x38, 0x25, 0x01 };

	buf[8] = enable;
	buf[9] = nanosic_wn8030_checksum8(&buf[2], 7);

	return regmap_bulk_write(nanosic->regmap, 0x5c, buf, sizeof(buf));
}







static int nanosic_wn8030_output_report(struct hid_device *hid, u8 *buf, size_t count)
{
	struct nanosic_wn8030 *nanosic = hid->driver_data;

	//print_hex_dump(KERN_INFO, "output_report: ", DUMP_PREFIX_NONE, 16, 1, buf, count, false);

	if (!count)
		return -EINVAL;

	if (buf[0] == 0x5) {
		int ret;
		if (count < 2)
			return -EINVAL;
		mutex_lock(&nanosic->io_lock);
		ret = nanosic->removing ? -ENODEV : !nanosic->ready ? -EAGAIN :
			nanosic_wn8030_set_caps_led(nanosic, buf[1]);
		mutex_unlock(&nanosic->io_lock);
		if (ret)
			return ret;
	}

	return count;
}

static struct hid_ll_driver nanosic_wn8030_hid_ll_driver = {
	.parse = nanosic_wn8030_hid_parse,
	.start = nanosic_wn8030_hid_start,
	.stop = nanosic_wn8030_hid_stop,
	.open = nanosic_wn8030_hid_open,
	.close = nanosic_wn8030_hid_close,
	.raw_request = nanosic_wn8030_raw_request,
	.output_report = nanosic_wn8030_output_report,
};

static void nanosic_wn8030_add_keyboard_hid(struct nanosic_wn8030 *nanosic)
{
	struct hid_device *hid;

	hid = hid_allocate_device();
	if (IS_ERR(hid)) {
		dev_err(nanosic->dev, "failed allocate keyboard hid device");
		nanosic->hid_keyboard = NULL;
		return;
	}

	hid->driver_data = nanosic;
	hid->ll_driver = &nanosic_wn8030_hid_ll_driver;
	hid->bus = BUS_I2C;
	hid->dev.parent = nanosic->dev;
	hid->vendor = 0x15D9;
	hid->product = 0x00A3;
	sprintf(hid->name, "%s", "Xiaomi Keyboard");

	if (hid_add_device(hid)) {
		dev_err(nanosic->dev, "failed add keyboard hid device");
		hid_destroy_device(hid);
		nanosic->hid_keyboard = NULL;
		return;
	}

	nanosic->hid_keyboard = hid;
}

static void nanosic_wn8030_add_touchpad_hid(struct nanosic_wn8030 *nanosic)
{
	struct hid_device *hid;

	hid = hid_allocate_device();
	if (IS_ERR(hid)) {
		dev_err(nanosic->dev, "failed allocate touchpad hid device");
		nanosic->hid_touchpad = NULL;
		return;
	}

	hid->driver_data = nanosic;
	hid->ll_driver = &nanosic_wn8030_hid_ll_driver;
	hid->bus = BUS_I2C;
	hid->dev.parent = nanosic->dev;
	hid->vendor = 0x15D9;
	hid->product = 0x00A1;
	sprintf(hid->name, "%s", "Xiaomi Touchpad");

	if (hid_add_device(hid)) {
		dev_err(nanosic->dev, "failed add touchpad hid device");
		hid_destroy_device(hid);
		nanosic->hid_touchpad = NULL;
		return;
	}

	nanosic->hid_touchpad = hid;
}

static void nanosic_wn8030_handle_vendor(struct nanosic_wn8030 *nanosic,
					 u8 *buf, size_t len)
{
	int state = sheng_nano_connection_state(buf + 3, len);
	bool attached = state == SHENG_NANO_KEYBOARD;

	if (state != SHENG_NANO_NO_UPDATE) {
		mutex_lock(&nanosic->conn_mutex);
		if (nanosic->removing) {
			mutex_unlock(&nanosic->conn_mutex);
			return;
		}
		/* The shipping provider leaves keyboard_plugin unchanged for docks. */
		if (state != SHENG_NANO_DOCK && nanosic->plugin_requested != attached) {
			nanosic->plugin_requested = attached;
			nanosic->plugin_retries = 0;
			mod_delayed_work(system_wq, &nanosic->plugin_worker, 0);
		}
		if (attached && !nanosic->keyboard_attached) {
			/* Caps LED state saved between reconnects by WN8030 */
			nanosic_wn8030_set_caps_led(nanosic, false);
			nanosic_wn8030_set_touchpad(nanosic, true);
			nanosic_wn8030_add_keyboard_hid(nanosic);
			nanosic_wn8030_add_touchpad_hid(nanosic);
			nanosic->keyboard_attached = true;
			schedule_delayed_work(&nanosic->wake_worker, msecs_to_jiffies(12000));
		} else if (!attached && nanosic->keyboard_attached) {
			cancel_delayed_work(&nanosic->wake_worker);
			if (nanosic->hid_keyboard) {
				hid_destroy_device(nanosic->hid_keyboard);
				nanosic->hid_keyboard = NULL;
			}
			if (nanosic->hid_touchpad) {
				hid_destroy_device(nanosic->hid_touchpad);
				nanosic->hid_touchpad = NULL;
			}
			nanosic->keyboard_attached = false;
		}
		mutex_unlock(&nanosic->conn_mutex);
	}
	/* Vendor reports, including auth challenges/replies, go to stock HAL. */

}

static irqreturn_t nanosic_wn8030_handler(int irq, void *data)
{
	struct nanosic_wn8030 *nano = data;
	u8 buf[XM_WN8030_I2C_READ], *p;
	size_t left, len;
	int ret;

	mutex_lock(&nano->io_lock);
	if (!nano->ready || nano->removing) {
		mutex_unlock(&nano->io_lock);
		return IRQ_HANDLED;
	}
	if (nano->suspended) {
		nano->suspended = false;
		mutex_unlock(&nano->io_lock);
		return IRQ_HANDLED;
	}
	ret = regmap_bulk_read(nano->regmap, 0x4c, buf, sizeof(buf));
	mutex_unlock(&nano->io_lock);
	if (ret) {
		dev_warn_ratelimited(nano->dev, "MCU read failed: %d\n", ret);
		return IRQ_HANDLED;
	}
	if ((buf[0] & 0x7f) != 0x57 ||
	    (buf[2] != 0x39 && buf[2] != 0x4a && buf[2] != 0x5b && buf[2] != 0x6c))
		return IRQ_HANDLED;
	p = buf + 3;
	left = sizeof(buf) - 3;
	while (left) {
		switch (*p) {
		case 0x02: len = 8; break;
		case 0x05: len = 9; break;
		case 0x06: len = 5; break;
		case 0x19: len = 21; break;
		case 0x22: len = 16; break;
		case 0x23: len = 32; break;
		case 0x24: case 0x26: len = left; break;
		default: return IRQ_HANDLED;
		}
		if (len > left)
			return IRQ_HANDLED;
		if ((*p == 0x05 || *p == 0x06) && nano->hid_keyboard)
			hid_input_report(nano->hid_keyboard, HID_INPUT_REPORT, p, len, 0);
		else if (*p == 0x19 && nano->hid_touchpad)
			hid_input_report(nano->hid_touchpad, HID_INPUT_REPORT, p, len, 0);
		else if (*p >= 0x22) {
			sheng_nano_broadcast(nano, p, len);
			if (*p == 0x22 || *p == 0x23 || *p == 0x24) {
				u8 vendor[XM_WN8030_I2C_READ] = {0};
				memcpy(vendor + 3, p, len);
				nanosic_wn8030_handle_vendor(nano, vendor, len);
			}
		}
		p += len;
		left -= len;
	}
	return IRQ_HANDLED;
}

static int nanosic_wn8030_check_boot_id(struct nanosic_wn8030 *nanosic)
{
	int ret;
	unsigned int boot_id;

	ret = regmap_write(nanosic->regmap, 0x5c, 0x04);
	if (ret) {
		dev_err(nanosic->dev, "failed to set read address\n");
		return ret;
	}

	ret = regmap_read(nanosic->regmap, 0x5c, &boot_id);
	if (ret) {
		dev_err(nanosic->dev, "failed to read bootloader id\n");
		return ret;
	}

	if (boot_id != 0xc8) {
		dev_err(nanosic->dev, "unexpected bootloader id 0x%x\n", boot_id);
		return -EINVAL;
	}

	return 0;
}

static int nanosic_wn8030_get_boot_state(struct nanosic_wn8030 *nanosic)
{
	int ret;
	unsigned int boot_state;

	ret = regmap_write(nanosic->regmap, 0x5c, 0x05);
	if (ret) {
		dev_err(nanosic->dev, "failed to set read address\n");
		return ret;
	}

	ret = regmap_read(nanosic->regmap, 0x5c, &boot_state);
	if (ret) {
		dev_err(nanosic->dev, "failed to read bootloader state\n");
		return ret;
	}

	return boot_state;
}

static int nanosic_wn8030_send_header(struct nanosic_wn8030 *nanosic, const u8 *fw_buf, u32 *ram_code_size)
{
	int ret;
	struct wn8030_header_cmd hdr_cmd = {0};
	struct wn8030_bin_header *bin_hdr = (struct wn8030_bin_header *)&fw_buf[WN8030_HEADER_ADDR];

	hdr_cmd.cmd = 0x06; /* header send cmd */
	memcpy(hdr_cmd.flag, bin_hdr->flag, sizeof(hdr_cmd.flag));
	hdr_cmd.chip_id = 0x8140;
	hdr_cmd.ram_code_source = 0x2345;
	hdr_cmd.ram_code_dest = 0x40;
	hdr_cmd.ram_code_size = bin_hdr->ram_code_size;
	*ram_code_size = bin_hdr->ram_code_size;
	hdr_cmd.code_entry = bin_hdr->code_entry;
	hdr_cmd.code_entry = bin_hdr->code_entry;
	hdr_cmd.pid = bin_hdr->pid;
	hdr_cmd.vid = bin_hdr->vid;
	hdr_cmd.major_version = bin_hdr->major_version;
	hdr_cmd.minor_version = bin_hdr->minor_version;
	hdr_cmd.image_size = 0;
	hdr_cmd.ram_code_checksum = nanosic_wn8030_checksum32(&fw_buf[WN8030_CODE_ADDR], hdr_cmd.ram_code_size);
	hdr_cmd.image_checksum = 0;
	hdr_cmd.header_checksum = nanosic_wn8030_checksum8((u8 *)&hdr_cmd + 1, 64);

	ret = regmap_bulk_write(nanosic->regmap, 0x5c, &hdr_cmd, sizeof(hdr_cmd));
	if (ret) {
		dev_err(nanosic->dev, "failed to send header\n");
		return ret;
	}

	ret = nanosic_wn8030_get_boot_state(nanosic);
	if (ret < 0)
		return ret;

	if (ret != 0x1) {
		dev_err(nanosic->dev, "unexpected bootloader state after sending header %d\n", ret);
		return -EINVAL;
	}

	return 0;
}

static int nanosic_wn8030_send_data(struct nanosic_wn8030 *nanosic, const u8 *fw_buf, u32 ram_code_size)
{
	int ret;
	struct wn8030_send_cmd send_cmd;
	unsigned int offset = 0;

	while (ram_code_size > offset) {
		unsigned int send_size;

		memset(&send_cmd, 0, sizeof(send_cmd));
		send_cmd.cmd = 0x07;
		send_cmd.ram_dest = cpu_to_be32(offset);

		if (ram_code_size - offset < 503)
			send_size = ram_code_size - offset;
		else
			send_size = 503;

		send_cmd.size = cpu_to_be32(send_size);
		memcpy(send_cmd.data, &fw_buf[WN8030_CODE_ADDR+offset], send_size);

		ret = regmap_bulk_write(nanosic->regmap, 0x5c, &send_cmd, sizeof(send_cmd));
		if (ret) {
			dev_err(nanosic->dev, "failed to send data to 0x%x\n", offset);
			return ret;
		}
		offset += send_size;
	}

	return 0;
}

static int nanosic_wn8030_load_fw(struct nanosic_wn8030 *nanosic)
{
	int ret;
	const struct firmware *firmware;
	unsigned int ram_code_size;

	/* Keep the verified RAM image across suspend. Stock ueventd resolves
	 * /odm/firmware on the first load; direct-only requests cannot find it.
	 * Resume reuses this cache without entering the firmware fallback. */
	firmware = nanosic->ram_firmware;
	ret = firmware ? 0 : request_firmware(&firmware, "MCU_Upgrade.bin", nanosic->dev);
	if (!ret && !nanosic->ram_firmware)
		nanosic->ram_firmware = firmware;
	if (ret) {
		dev_err(nanosic->dev, "failed to load MCU firmware\n");
		return ret;
	}

	if (firmware->size < 0xA000) {
		dev_err(nanosic->dev, "invalid firmware size\n");
		ret = -EINVAL;
		goto exit;
	}

	if (strncmp(&firmware->data[0x7FC0], "NANO IC", 7) != 0) {
		dev_err(nanosic->dev, "invalid firmware header\n");
		ret = -EINVAL;
		goto exit;
	}

	ram_code_size = get_unaligned_le32(firmware->data + WN8030_HEADER_ADDR +
		offsetof(struct wn8030_bin_header, ram_code_size));
	if (!ram_code_size || (ram_code_size & 3) ||
	    ram_code_size > firmware->size - WN8030_CODE_ADDR) {
		ret = -EINVAL;
		goto exit;
	}
	ret = nanosic_wn8030_send_header(nanosic, firmware->data, &ram_code_size);
	if (ret)
		goto exit;

	ret = nanosic_wn8030_send_data(nanosic, firmware->data, ram_code_size);
	if (ret)
		goto exit;

	ret = regmap_write(nanosic->regmap, 0x5c, 0x08);
	if (ret) {
		dev_err(nanosic->dev, "failed to start firmware verification\n");
		goto exit;
	}

	msleep(10);

	ret = nanosic_wn8030_get_boot_state(nanosic);
	if (ret < 0)
		goto exit;

	if (ret != 0x3) {
		dev_err(nanosic->dev, "bootloader failed to verify firmware %d\n", ret);
		ret = -EINVAL;
		goto exit;
	}

	ret = regmap_write(nanosic->regmap, 0x5c, 0x09);
	if (ret) {
		dev_err(nanosic->dev, "failed to boot firmware\n");
		goto exit;
	}

	msleep(50);

exit:
	/* Released with the transport lifetime, after all workers stop. */

	return ret;
}

static int nanosic_wn8030_power_on(struct nanosic_wn8030 *nanosic)
{
	int ret;

	ret = regulator_bulk_enable(WN8030_NUM_SUPPLIES,
				    nanosic->supplies);
	if (ret) {
		dev_err(nanosic->dev, "failed to enable regulators\n");
		return ret;
	}

	gpiod_set_value_cansleep(nanosic->reset_gpio, 0);
	msleep(20); /* On Pad 6S Pro we only wait for WN8030 bootrom start */
	gpiod_set_value_cansleep(nanosic->sleep_gpio, 0);

	return 0;
}

static void nanosic_wn8030_power_off(struct nanosic_wn8030 *nanosic)
{
	gpiod_set_value_cansleep(nanosic->sleep_gpio, 1);
	gpiod_set_value_cansleep(nanosic->reset_gpio, 1);
	msleep(10);
	regulator_bulk_disable(WN8030_NUM_SUPPLIES, nanosic->supplies);
}

static void nanosic_wn8030_wake_worker(struct work_struct *data)
{
	struct nanosic_wn8030 *nanosic =
		container_of(data, struct nanosic_wn8030, wake_worker.work);

	mutex_lock(&nanosic->io_lock);
	if (nanosic->ready && !nanosic->removing && nanosic->keyboard_attached && !nanosic->suspended) {
		nanosic_wn8030_set_kb_power(nanosic, true);
		schedule_delayed_work(&nanosic->wake_worker, msecs_to_jiffies(12000));
	}
	mutex_unlock(&nanosic->io_lock);
}

/* SPDX-License-Identifier: GPL-2.0-only */
/* Replaces reference probe/PM code; uses the original sheng DT unchanged. */
static void sheng_nano_plugin_worker(struct work_struct *work)
{
	struct nanosic_wn8030 *nano =
		container_of(work, struct nanosic_wn8030, plugin_worker.work);
	int wanted, ret;

	mutex_lock(&nano->conn_mutex);
	if (nano->removing || nano->plugin_requested < 0 ||
	    nano->plugin_requested == nano->plugin_sent) {
		mutex_unlock(&nano->conn_mutex);
		return;
	}
	wanted = nano->plugin_requested;
	mutex_unlock(&nano->conn_mutex);
	ret = qti_set_keyboard_plugin(wanted);
	mutex_lock(&nano->conn_mutex);
	if (!ret) {
		nano->plugin_sent = wanted;
		nano->plugin_retries = 0;
	} else {
		nano->plugin_retries++;
	}
	if (!nano->removing && nano->plugin_requested != nano->plugin_sent &&
	    nano->plugin_retries < 30)
		mod_delayed_work(system_wq, &nano->plugin_worker, ret ? HZ : 0);
	mutex_unlock(&nano->conn_mutex);
	if (!ret)
		do { } while (0);
	else
		dev_warn_ratelimited(nano->dev, "Keyboard charger event %d failed: %d\n", wanted, ret);
}

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
		/* A reset loses MCU settings while the HID devices may survive. */
		if (nano->keyboard_attached) {
			nanosic_wn8030_set_touchpad(nano, true);
			nanosic_wn8030_set_kb_power(nano, true);
			mod_delayed_work(system_wq, &nano->wake_worker,
				msecs_to_jiffies(12000));
		}
		enable_irq(nano->client->irq);
		do { } while (0);
	} else if ((ret == -ENOENT || ret == -EAGAIN) && nano->fw_attempts < 60) {
		/* /odm may not be mounted, or PM may still block firmware requests. */
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
	int ret;

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
	INIT_DELAYED_WORK(&nano->plugin_worker, sheng_nano_plugin_worker);
	nano->plugin_requested = -1;
	nano->plugin_sent = -1;

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
	/* Match shipping Nanosic_regulator_init's board-version selection.
	 * L6B and L12B are alternatives, not a three-rail bulk supply. */
	{
		struct device_node *chosen = of_find_node_by_path("/chosen");
		const char *bootargs, *digital_key;

		ret = chosen ? of_property_read_string(chosen, "bootargs", &bootargs) : -ENOENT;
		if (!ret)
			ret = sheng_nano_digital_supply_key(bootargs, &digital_key);
		of_node_put(chosen);
		if (ret)
			goto free;
		ret = of_property_read_string(dev->of_node, "nanosic,vdd-name",
					      &nano->supplies[0].supply);
		if (!ret)
			ret = of_property_read_string(dev->of_node, digital_key,
						      &nano->supplies[1].supply);
		if (ret)
			goto free;
		do { } while (0);
	}
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
	do { } while (0);
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
	cancel_delayed_work_sync(&nano->plugin_worker);
	if (nano->plugin_sent == 1)
		qti_set_keyboard_plugin(0);
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
		schedule_delayed_work(&nano->fw_worker, msecs_to_jiffies(100));
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
		schedule_delayed_work(&nano->fw_worker, msecs_to_jiffies(100));
	} else {
		mutex_lock(&nano->io_lock);
		nanosic_wn8030_set_kb_power(nano, true);
		/* suspend cancels this keepalive; resume must start it again. */
		if (nano->keyboard_attached)
			mod_delayed_work(system_wq, &nano->wake_worker,
				msecs_to_jiffies(12000));
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
