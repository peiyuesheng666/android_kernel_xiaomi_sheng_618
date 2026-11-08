// SPDX-License-Identifier: Apache-2.0
#define LOG_TAG "ShengCameraOrientation"
#include <hardware/camera_common.h>
#include <log/log.h>
#include <system/camera_metadata.h>

#include <cerrno>
#include <cstring>
#include <dlfcn.h>
#include <map>
#include <mutex>

// OEM HMI has a standard 344-byte prefix and a 32-byte private tail. Preserve
// the entire observed object, including opaque extension pointers.
struct OemCameraModule {
    camera_module_t api;
    void* extension[4];
};
extern "C" {
__attribute__((visibility("default"))) OemCameraModule HAL_MODULE_INFO_SYM = {};
}

namespace {
camera_module_t* original = nullptr;

// Match the observed OEM back/front mounting pairs. Synthetic zero-degree
// devices and external cameras retain their original metadata.
bool correctedOrientation(uint8_t facing, int32_t old, int32_t* corrected) {
    if ((facing == ANDROID_LENS_FACING_BACK && old == 90) ||
        (facing == ANDROID_LENS_FACING_FRONT && old == 270)) {
        *corrected = (old + 270) % 360;
        return true;
    }
    return false;
}

struct MetadataCache {
    std::mutex mutex;
    std::map<const camera_metadata_t*, camera_metadata_t*> copies;
};

int correctedMetadata(const camera_metadata_t* input, const camera_metadata_t** output) {
    *output = input;
    if (!input) return 0;
    camera_metadata_ro_entry_t facing{}, orientation{};
    if (find_camera_metadata_ro_entry(input, ANDROID_LENS_FACING, &facing) ||
        find_camera_metadata_ro_entry(input, ANDROID_SENSOR_ORIENTATION, &orientation) ||
        facing.type != TYPE_BYTE || facing.count != 1 ||
        orientation.type != TYPE_INT32 || orientation.count != 1) return 0;
    int32_t corrected;
    if (!correctedOrientation(facing.data.u8[0], orientation.data.i32[0], &corrected)) return 0;
    // Camera module characteristics must remain valid for the provider lifetime.
    // Keep the OEM buffer read-only and retain one stable clone per OEM buffer.
    static MetadataCache* cache = new MetadataCache;
    std::lock_guard<std::mutex> lock(cache->mutex);
    auto found = cache->copies.find(input);
    if (found != cache->copies.end()) {
        *output = found->second;
        return 0;
    }
    camera_metadata_t* copy = clone_camera_metadata(input);
    if (!copy) return -ENOMEM;
    int result = update_camera_metadata_entry(copy, orientation.index, &corrected, 1, nullptr);
    if (result) {
        free_camera_metadata(copy);
        return -EINVAL;
    }
    cache->copies.emplace(input, copy);
    *output = copy;
    return 0;
}

int getCameraInfo(int id, camera_info* info) {
    int result = original->get_camera_info(id, info);
    if (result || !info) return result;
    result = correctedMetadata(info->static_camera_characteristics,
                               &info->static_camera_characteristics);
    if (result) return result;
    camera_metadata_ro_entry_t entry{};
    if (info->static_camera_characteristics &&
        !find_camera_metadata_ro_entry(info->static_camera_characteristics,
                                       ANDROID_SENSOR_ORIENTATION, &entry) &&
        entry.type == TYPE_INT32 && entry.count == 1) info->orientation = entry.data.i32[0];
    return 0;
}

int getPhysicalInfo(int id, camera_metadata_t** metadata) {
    int result = original->get_physical_camera_info(id, metadata);
    if (result || !metadata) return result;
    const camera_metadata_t* corrected = nullptr;
    result = correctedMetadata(*metadata, &corrected);
    if (!result) *metadata = const_cast<camera_metadata_t*>(corrected);
    return result;
}

int openCamera(const hw_module_t*, const char* name, hw_device_t** device) {
    return original->common.methods->open(&original->common, name, device);
}

int openLegacy(const hw_module_t*, const char* name, uint32_t version, hw_device_t** device) {
    return original->open_legacy(&original->common, name, version, device);
}

hw_module_methods_t methods = {.open = openCamera};

#ifndef SHENG_CAMERA_TEST
__attribute__((constructor)) void initialize() {
    static_assert(sizeof(camera_module_t) == 344 && sizeof(OemCameraModule) == 376,
                  "Re-review OEM module ABI if the header changes");
    void* handle = dlopen("/odm/lib64/hw/camera.xiaomi.so", RTLD_NOW | RTLD_LOCAL);
    if (!handle) {
        ALOGE("Cannot load original camera module: %s", dlerror());
        return;
    }
    auto* raw = static_cast<OemCameraModule*>(dlsym(handle, HAL_MODULE_INFO_SYM_AS_STR));
    auto* module = raw ? &raw->api : nullptr;
    if (!module || module->common.tag != HARDWARE_MODULE_TAG || !module->common.id ||
        std::strcmp(module->common.id, CAMERA_HARDWARE_MODULE_ID) ||
        module->common.module_api_version < CAMERA_MODULE_API_VERSION_2_4 ||
        module->common.module_api_version > CAMERA_MODULE_API_VERSION_2_5 ||
        !module->get_camera_info || !module->common.methods || !module->common.methods->open) {
        ALOGE("Unexpected original camera module ABI");
        dlclose(handle);
        return;
    }
    original = module;
    original->common.dso = handle;
    HAL_MODULE_INFO_SYM = *raw;
    HAL_MODULE_INFO_SYM.api.common.methods = &methods;
    HAL_MODULE_INFO_SYM.api.get_camera_info = getCameraInfo;
    if (original->open_legacy) HAL_MODULE_INFO_SYM.api.open_legacy = openLegacy;
    if (original->get_physical_camera_info) HAL_MODULE_INFO_SYM.api.get_physical_camera_info = getPhysicalInfo;
    ALOGI("Loaded OEM module with landscape sensor orientation adapter");
}
#endif
}  // namespace
