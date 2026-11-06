# SPDX-License-Identifier: Apache-2.0
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base.mk)
$(call inherit-product, device/xiaomi/sheng/device.mk)
TARGET_EXCLUDES_AUDIOFX := true
$(call inherit-product, vendor/lineage/config/common_full_tablet_wifionly.mk)

# Bring-up builds need ADB before the display/setup wizard is usable.
PRODUCT_NOT_DEBUGGABLE_IN_USERDEBUG := false

PRODUCT_NAME := lineage_sheng
PRODUCT_DEVICE := sheng
PRODUCT_BRAND := Xiaomi
PRODUCT_MANUFACTURER := Xiaomi
# The supplied CN firmware identifies 24018RPACC; 24018RPACG is the global SKU.
PRODUCT_MODEL := 24018RPACC
PRODUCT_MARKETNAME := Xiaomi Pad 6S Pro 12.4

PRODUCT_GMS_CLIENTID_BASE := android-xiaomi
