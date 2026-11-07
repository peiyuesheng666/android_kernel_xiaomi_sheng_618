# SPDX-License-Identifier: Apache-2.0
LOCAL_PATH := $(call my-dir)

include $(CLEAR_VARS)
LOCAL_MODULE := sheng-tablet-bootclasspath
LOCAL_MODULE_CLASS := ETC
LOCAL_MODULE_PATH := $(TARGET_OUT_SYSTEM_EXT_ETC)/sheng
LOCAL_MODULE_STEM := bootclasspath.pb
LOCAL_REQUIRED_MODULES := sheng-tablet-compat
LOCAL_PREBUILT_MODULE_FILE := $(call intermediates-dir-for,ETC,sheng-tablet-bootclasspath)/bootclasspath.pb
include $(BUILD_PREBUILT)

sheng_tablet_classpath_out := $(call intermediates-dir-for,ETC,sheng-tablet-bootclasspath)/bootclasspath.pb
$(sheng_tablet_classpath_out): $(TARGET_OUT_ETC)/classpaths/bootclasspath.pb $(LOCAL_PATH)/merge_classpath.py
	@mkdir -p $(dir $@)
	$(hide) python3 device/xiaomi/sheng/interfaces/compat/tablet/merge_classpath.py $< $@
