DEVICE_PATH := device/xiaomi/sheng

#
# Copyright (C) 2024-2025 The LineageOS Project
#
# SPDX-License-Identifier: Apache-2.0
#


# A/B
AB_OTA_PARTITIONS := \
    boot \
    dtbo \
    init_boot \
    odm \
    product \
    recovery \
    system \
    system_dlkm \
    system_ext \
    vbmeta \
    vbmeta_system \
    vendor \
    vendor_boot \
    vendor_dlkm

# Architecture
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-2a-dotprod
TARGET_CPU_ABI := arm64-v8a
TARGET_CPU_VARIANT := kryo

# Audio
AUDIO_FEATURE_ENABLED_PROXY_DEVICE := true
AUDIO_FEATURE_ENABLED_DTS_EAGLE := false
AUDIO_FEATURE_ENABLED_PAL_HIDL := true
AUDIO_FEATURE_ENABLED_AGM_HIDL := true
AUDIO_FEATURE_ENABLED_HW_ACCELERATED_EFFECTS := false
AUDIO_FEATURE_ENABLED_DLKM := true
AUDIO_FEATURE_ENABLED_INSTANCE_ID := true
AUDIO_FEATURE_ENABLED_KEEP_ALIVE := true
AUDIO_FEATURE_ENABLED_GEF_SUPPORT := true
AUDIO_FEATURE_ENABLED_SVA_MULTI_STAGE := true
BOARD_SUPPORTS_SOUND_TRIGGER := true
BOARD_SUPPORTS_OPENSOURCE_STHAL := true
TARGET_USES_QCOM_MM_AUDIO := true

# Bootloader
TARGET_NO_BOOTLOADER := true

# Filesystem
TARGET_FS_CONFIG_GEN := $(DEVICE_PATH)/configs/config.fs

# Hardware
BOARD_USES_QCOM_HARDWARE := true

# Kernel
BOARD_KERNEL_BASE        := 0x00000000
BOARD_KERNEL_PAGESIZE    := 4096

BOARD_KERNEL_CMDLINE := \
    mtdoops.fingerprint=$(LINEAGE_VERSION) \
    swinfo.fingerprint=$(LINEAGE_VERSION)

BOARD_BOOTCONFIG := \
    androidboot.console=ttyMSM0 \
    androidboot.hardware=qcom \
    androidboot.memcg=1 \
    androidboot.usbcontroller=a600000.dwc3

BOARD_INCLUDE_DTB_IN_BOOTIMG := true
BOARD_RAMDISK_USE_LZ4 := true

BOARD_BOOT_HEADER_VERSION := 4
BOARD_MKBOOTIMG_ARGS += --header_version $(BOARD_BOOT_HEADER_VERSION)

BOARD_INIT_BOOT_HEADER_VERSION := 4
BOARD_MKBOOTIMG_INIT_ARGS += --header_version $(BOARD_INIT_BOOT_HEADER_VERSION)

BOARD_USES_GENERIC_KERNEL_IMAGE := true
BOARD_KERNEL_IMAGE_NAME := Image


# Kernel (modules)
TARGET_KERNEL_EXT_MODULE_ROOT := kernel/xiaomi/sm8550-modules
# Stock BSP selected by module-plan.json; the kernel core stays LineageOS.
TARGET_KERNEL_EXT_MODULES := ../../../device/xiaomi/sheng/kernel/stock-modules
SYSTEM_KERNEL_MODULES := zsmalloc.ko zram.ko
BOARD_SYSTEM_KERNEL_MODULES_LOAD := zsmalloc.ko zram.ko

# A/B recovery ramdisk is prepended to vendor_boot. Its module metadata can be
# overwritten by vendor_boot, so both ramdisks need the recovery dependency set.
# The normal-boot modules.load remains restricted to the first-stage list.
BOOT_KERNEL_MODULES := $(strip $(shell cat $(DEVICE_PATH)/configs/modules/modules.list.recovery))
RECOVERY_KERNEL_MODULES := $(strip $(shell cat $(DEVICE_PATH)/configs/modules/modules.list.recovery))
BOARD_RECOVERY_KERNEL_MODULES_LOAD := $(strip $(shell cat $(DEVICE_PATH)/configs/modules/modules.load.recovery))
BOARD_VENDOR_KERNEL_MODULES_LOAD := $(strip $(shell cat $(DEVICE_PATH)/configs/modules/modules.load.vendor_dlkm))
BOARD_VENDOR_RAMDISK_KERNEL_MODULES_LOAD := $(strip $(shell cat $(DEVICE_PATH)/configs/modules/modules.load.first_stage))
BOARD_VENDOR_RAMDISK_RECOVERY_KERNEL_MODULES_LOAD  := $(strip $(shell cat $(DEVICE_PATH)/configs/modules/modules.load.recovery))

# Partitions

BOARD_FLASH_BLOCK_SIZE := 262144 # (BOARD_KERNEL_PAGESIZE * 64)

BOARD_USES_METADATA_PARTITION := true

SHENG_SYSTEM_PARTITIONS := product system system_ext system_dlkm
SHENG_VENDOR_PARTITIONS := odm vendor vendor_dlkm

BOARD_QTI_DYNAMIC_PARTITIONS_PARTITION_LIST := $(SHENG_SYSTEM_PARTITIONS) $(SHENG_VENDOR_PARTITIONS)
BOARD_SUPER_PARTITION_GROUPS := qti_dynamic_partitions

$(foreach p, $(call to-upper, $(SHENG_SYSTEM_PARTITIONS)), \
    $(eval BOARD_$(p)IMAGE_FILE_SYSTEM_TYPE := ext4))

$(foreach p, $(call to-upper, $(SHENG_VENDOR_PARTITIONS)), \
    $(eval BOARD_$(p)IMAGE_FILE_SYSTEM_TYPE := erofs))

$(foreach p, $(call to-upper, $(BOARD_QTI_DYNAMIC_PARTITIONS_PARTITION_LIST)), \
    $(eval TARGET_COPY_OUT_$(p) := $(call to-lower, $(p))))

BOARD_PRODUCTIMAGE_MINIMAL_PARTITION_RESERVED_SIZE := false
include vendor/lineage/config/BoardConfigReservedSize.mk

# Platform
TARGET_BOARD_PLATFORM := kalama
TARGET_BOOTLOADER_BOARD_NAME := kalama

# Recovery
BOARD_EXCLUDE_KERNEL_FROM_RECOVERY_IMAGE := true
TARGET_RECOVERY_PIXEL_FORMAT := RGBX_8888
# Test the available Qualcomm atomic backend for sheng's dual-DSI DSC panel.
# The legacy backend renders a valid framebuffer but the panel scanout fails.
$(call soong_config_set_bool,recovery,target_recovery_uses_qti_drm,true)
TARGET_USERIMAGES_USE_EXT4 := true
TARGET_USERIMAGES_USE_F2FS := true

# RIL

# SEPolicy
include device/qcom/sepolicy_vndr/SEPolicy.mk

# System properties

# VINTF
DEVICE_MATRIX_FILE := hardware/qcom-caf/common/compatibility_matrix.xml
DEVICE_FRAMEWORK_COMPATIBILITY_MATRIX_FILE += \
    hardware/qcom-caf/common/vendor_framework_compatibility_matrix.xml \
    hardware/xiaomi/vintf/xiaomi_framework_compatibility_matrix.xml \
    $(DEVICE_PATH)/configs/vintf/framework_dolby_matrix.xml

DEVICE_FRAMEWORK_MANIFEST_FILE += $(DEVICE_PATH)/configs/vintf/framework_manifest.xml

# Vendor security patch

# Verified Boot
BOARD_AVB_ENABLE := true
BOARD_AVB_MAKE_VBMETA_IMAGE_ARGS += --flags 3
BOARD_MOVE_GSI_AVB_KEYS_TO_VENDOR_BOOT := true

BOARD_AVB_VBMETA_SYSTEM := product system system_ext
BOARD_AVB_VBMETA_SYSTEM_KEY_PATH := external/avb/test/data/testkey_rsa2048.pem
BOARD_AVB_VBMETA_SYSTEM_ALGORITHM := SHA256_RSA2048
BOARD_AVB_VBMETA_SYSTEM_ROLLBACK_INDEX := 1
BOARD_AVB_VBMETA_SYSTEM_ROLLBACK_INDEX_LOCATION := 1

# WiFi
BOARD_WLAN_DEVICE := qcwcn
BOARD_HOSTAPD_DRIVER := NL80211
BOARD_HOSTAPD_PRIVATE_LIB := lib_driver_cmd_$(BOARD_WLAN_DEVICE)
BOARD_WPA_SUPPLICANT_DRIVER := NL80211
BOARD_WPA_SUPPLICANT_PRIVATE_LIB := lib_driver_cmd_$(BOARD_WLAN_DEVICE)
WIFI_DRIVER_DEFAULT := qca_cld3
WIFI_DRIVER_STATE_CTRL_PARAM := "/dev/wlan"
WIFI_DRIVER_STATE_OFF := "OFF"
WIFI_DRIVER_STATE_ON := "ON"
WIFI_HIDL_FEATURE_AWARE := true
WIFI_HIDL_FEATURE_DUAL_INTERFACE := true
WIFI_FEATURE_HOSTAPD_11AX := true
WIFI_HIDL_UNIFIED_SUPPLICANT_SERVICE_RC_ENTRY := true
WPA_SUPPLICANT_VERSION := VER_0_8_X


# SPDX-License-Identifier: Apache-2.0

TARGET_SCREEN_DENSITY := 400
TARGET_OTA_ASSERT_DEVICE := sheng

# Sizes verified against this sheng fastboot package and sparse-super metadata.
BOARD_BOOTIMAGE_PARTITION_SIZE := 100663296
BOARD_DTBOIMG_PARTITION_SIZE := 16777216
BOARD_INIT_BOOT_IMAGE_PARTITION_SIZE := 8388608
BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE := 100663296
BOARD_RECOVERYIMAGE_PARTITION_SIZE := 104857600
BOARD_SUPER_PARTITION_SIZE := 11811160064
BOARD_QTI_DYNAMIC_PARTITIONS_SIZE := 11800674304

# The kernel remains the official LineageOS SM8550 source. The sheng fragment,
# board DT and device-only modules still require integration and validation.
TARGET_KERNEL_SOURCE := kernel/xiaomi/sm8550
TARGET_KERNEL_CONFIG := gki_defconfig vendor/kalama_GKI.config
TARGET_KERNEL_CONFIG_EXT := $(DEVICE_PATH)/configs/kernel/sheng.config
# Kernel 5.15's C90 UAPI tests need POSIX timespec declarations from host libc.
# Keep the header tests enabled and retain the original UAPI layouts.
TARGET_KERNEL_ADDITIONAL_FLAGS += USERCFLAGS=-D_POSIX_C_SOURCE=200809L
# Header-only BSP snapshot keeps kernel declarations out of the userspace ABI.
# The normal headers_install and C90 header tests remain enabled.
TARGET_KERNEL_ADDITIONAL_FLAGS += ext-mod-dir=../../../device/xiaomi/sheng/kernel/uapi
TARGET_AUTO_COLLECT_KERNEL_MODULE_DEPS := false


# Reuse the supplied sheng hardware descriptions for the initial 5.15 port.
BOARD_USES_QCOM_MERGE_DTBS_SCRIPT := false
TARGET_NEEDS_DTBOIMAGE := false
BOARD_PREBUILT_DTBIMAGE_DIR := device/xiaomi/sheng-kernel/dtb
BOARD_PREBUILT_DTBOIMAGE := device/xiaomi/sheng-kernel/dtbo.img
BOARD_KERNEL_CMDLINE += video=vfb:640x400,bpp=32,memsize=3072000 disable_dma32=on

ENABLE_VENDOR_RIL_SERVICE := false
VENDOR_SECURITY_PATCH := 2026-02-01
BOARD_VENDOR_SEPOLICY_DIRS += $(DEVICE_PATH)/sepolicy/vendor
SYSTEM_EXT_PUBLIC_SEPOLICY_DIRS += $(DEVICE_PATH)/sepolicy/system_ext/public
SYSTEM_EXT_PRIVATE_SEPOLICY_DIRS += $(DEVICE_PATH)/sepolicy/system_ext/private
TARGET_VENDOR_PROP := $(DEVICE_PATH)/properties/vendor.prop
TARGET_ODM_PROP := $(DEVICE_PATH)/properties/odm.prop
TARGET_SYSTEM_PROP := $(DEVICE_PATH)/properties/system.prop
TARGET_PRODUCT_PROP := $(DEVICE_PATH)/properties/product.prop
TARGET_SYSTEM_EXT_PROP := $(DEVICE_PATH)/properties/system_ext.prop
TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/rootdir/etc/fstab.qcom

DEVICE_MANIFEST_FILE := \
    $(DEVICE_PATH)/configs/vintf/manifest_kalama.xml \
    $(DEVICE_PATH)/configs/vintf/manifest_xiaomi.xml

include vendor/xiaomi/sheng/BoardConfigVendor.mk
