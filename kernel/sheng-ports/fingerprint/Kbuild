# SPDX-License-Identifier: GPL-2.0-only
ccflags-y += -include $(src)/../../tp-autoconf.h
ccflags-y += -I$(src)/../../soc/include -I$(src)/../../vendor/qcom/opensource/display-drivers/include
obj-m += fpc1552.o xiaomifp.o
fpc1552-y := fpc1020_tee.o
xiaomifp-y := xiaomi_fingerprint.o
