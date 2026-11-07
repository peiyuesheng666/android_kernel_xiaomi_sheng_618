// SPDX-License-Identifier: Apache-2.0
#define LOG_TAG "ShengDolbyCodec2"

#include <C2Component.h>
#include <binder/ProcessState.h>
#include <codec2/hidl/1.0/ComponentStore.h>
#include <hidl/HidlTransportSupport.h>
#include <log/log.h>
#include <signal.h>

#include <memory>

namespace android {
// Supplied by the original Dolby store library selected for each executable.
std::shared_ptr<C2ComponentStore> GetCodec2DolbyComponentStore();
}

int main() {
    using android::hardware::media::c2::V1_0::utils::ComponentStore;
    signal(SIGPIPE, SIG_IGN);
    android::ProcessState::initWithDriver("/dev/vndbinder");
    android::ProcessState::self()->startThreadPool();
    android::hardware::configureRpcThreadpool(8, true);

    auto implementation = android::GetCodec2DolbyComponentStore();
    if (!implementation) {
        ALOGE("%s: Dolby store factory returned null", SHENG_CODEC2_INSTANCE);
        return 1;
    }
    // Allocate with the same current headers as libcodec2_hidl. The stock main
    // embeds sizeof(ComponentStore)=264, which no longer covers this object.
    auto store = android::sp<ComponentStore>::make(implementation);
    if (store->status() != C2_OK) {
        ALOGE("%s: store initialization failed: %d", SHENG_CODEC2_INSTANCE, store->status());
        return 1;
    }
    const android::status_t status = store->registerAsService(SHENG_CODEC2_INSTANCE);
    if (status != android::OK) {
        ALOGE("%s: service registration failed: %d", SHENG_CODEC2_INSTANCE, status);
        return 1;
    }
    ALOGI("%s: registered, ComponentStore size=%zu", SHENG_CODEC2_INSTANCE,
          sizeof(ComponentStore));
    android::hardware::joinRpcThreadpool();
    return 1;
}
