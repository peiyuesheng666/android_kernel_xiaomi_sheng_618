# SPDX-License-Identifier: GPL-2.0-only
ccflags-y += -include $(src)/../../tp-autoconf.h
ccflags-y += -I$(src)/../../soc/include -I$(src)/../../vendor/qcom/opensource/display-drivers/include
ccflags-y += -DTOUCH_THP_SUPPORT=1 -DTOUCH_IS_TDDI -DTOUCH_STYLUS_SUPPORT -DDISABLE_POWER_STATUS
ccflags-y += -DCONFIG_TOUCHSCREEN_NVT_DEBUG_FS=1
ccflags-y += -Wno-missing-prototypes -Wno-missing-declarations
obj-m += xiaomi_touch.o nt36532_touch.o
xiaomi_touch-y := xiaomi/xiaomi_touch_knock_data.o xiaomi/xiaomi_touch_core.o xiaomi/xiaomi_touch_proc.o xiaomi/xiaomi_touch_operations.o xiaomi/xiaomi_touch_sys.o xiaomi/xiaomi_touch_mode.o xiaomi/xiaomi_touch_evdev.o xiaomi/xiaomi_touch_device.o
nt36532_touch-y := p81/nt36532/nt36xxx.o p81/nt36532/nt36xxx_fw_update.o p81/nt36532/nt36xxx_ext_proc.o p81/nt36532/nt36xxx_mp_ctrlram.o
