// SPDX-License-Identifier: Apache-2.0
// Preserve the tablet's four display angles while delegating audio to the
// unchanged upstream Qualcomm HAL. No stream, gain or effect callbacks change.
#define LOG_TAG "ShengAudioRotation"
#include <hardware/audio.h>
#include <cutils/str_parms.h>
#include <dlfcn.h>
#include <errno.h>
#include <log/log.h>
#include <mutex>
#include <stdlib.h>
#include <string.h>
#include "PalApi.h"

namespace {
std::mutex openMutex;
void* upstreamHandle = nullptr;
const hw_module_t* upstreamModule = nullptr;
int (*upstreamSetParameters)(audio_hw_device*, const char*) = nullptr;

int setParameters(audio_hw_device* device, const char* parameters) {
    if (!parameters) return -EINVAL;
    str_parms* parsed = str_parms_create_str(parameters);
    if (!parsed) return -ENOMEM;
    int degrees = 0;
    const bool hasRotation = str_parms_get_int(parsed, "rotation", &degrees) >= 0;
    if (!hasRotation) {
        str_parms_destroy(parsed);
        return upstreamSetParameters(device, parameters);
    }
    if (degrees != 0 && degrees != 90 && degrees != 180 && degrees != 270) {
        str_parms_destroy(parsed);
        return -EINVAL;
    }
    // The phone HAL collapses 0/90/180 into one state. Remove this key only;
    // all accompanying parameters still reach its original implementation.
    str_parms_del(parsed, "rotation");
    char* remaining = str_parms_to_str(parsed);
    str_parms_destroy(parsed);
    if (!remaining) return -ENOMEM;
    int status = upstreamSetParameters(device, remaining);
    free(remaining);
    pal_param_device_rotation_t rotation = {
        .rotation_type = static_cast<pal_speaker_rotation_type>(
                PAL_SPEAKER_ROTATION_SHENG_0 + degrees / 90),
    };
    const int rotationStatus = pal_set_param(PAL_PARAM_ID_DEVICE_ROTATION,
            &rotation, sizeof(rotation));
    ALOGI("display rotation=%d quad speaker update=%d", degrees, rotationStatus);
    return status ? status : rotationStatus;
}

int openDevice(const hw_module_t*, const char* name, hw_device_t** device) {
    if (!name || !device || strcmp(name, AUDIO_HARDWARE_INTERFACE)) return -EINVAL;
    std::lock_guard<std::mutex> lock(openMutex);
    if (!upstreamHandle) {
        upstreamHandle = dlopen("/vendor/lib64/hw/audio.primary.kalama.so", RTLD_NOW | RTLD_LOCAL);
        if (!upstreamHandle) {
            ALOGE("cannot load upstream HAL: %s", dlerror());
            return -ENODEV;
        }
        upstreamModule = static_cast<const hw_module_t*>(
                dlsym(upstreamHandle, HAL_MODULE_INFO_SYM_AS_STR));
        if (!upstreamModule || !upstreamModule->id ||
                strcmp(upstreamModule->id, AUDIO_HARDWARE_MODULE_ID) ||
                !upstreamModule->methods || !upstreamModule->methods->open) {
            dlclose(upstreamHandle);
            upstreamHandle = nullptr;
            upstreamModule = nullptr;
            return -EINVAL;
        }
    }
    int status = upstreamModule->methods->open(upstreamModule, name, device);
    if (status || !*device) return status ? status : -ENODEV;
    auto* audio = reinterpret_cast<audio_hw_device*>(*device);
    if (audio->set_parameters != setParameters) {
        upstreamSetParameters = audio->set_parameters;
        audio->set_parameters = setParameters;
    }
    return 0;
}
hw_module_methods_t methods = {.open = openDevice};
}  // namespace

extern "C" {
audio_module HAL_MODULE_INFO_SYM = {
    .common = {
        .tag = HARDWARE_MODULE_TAG,
        .module_api_version = AUDIO_MODULE_API_VERSION_0_1,
        .hal_api_version = HARDWARE_HAL_API_VERSION,
        .id = AUDIO_HARDWARE_MODULE_ID,
        .name = "Sheng quad speaker rotation",
        .author = "The LineageOS Project",
        .methods = &methods,
    },
};
}
