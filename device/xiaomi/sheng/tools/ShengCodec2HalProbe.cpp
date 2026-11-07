// SPDX-License-Identifier: Apache-2.0
// Read both original stores and create interfaces without starting a codec.
#include <android/hardware/media/c2/1.0/IComponentStore.h>
#include <binder/ProcessState.h>
#include <hidl/HidlTransportSupport.h>

#include <cstdio>
#include <string>
#include <vector>

int main() {
    using namespace android::hardware::media::c2::V1_0;
    android::ProcessState::initWithDriver("/dev/vndbinder");
    android::hardware::configureRpcThreadpool(2, false);
    for (const char* instance : {"dolby", "default1"}) {
        auto store = IComponentStore::tryGetService(instance);
        if (!store) {
            std::fprintf(stderr, "%s: service unavailable\n", instance);
            return 1;
        }
        bool listed = false;
        std::vector<std::string> names;
        auto result = store->listComponents([&](Status status, const auto& traits) {
            listed = status == Status::OK;
            std::printf("%s: list status=%d components=%zu\n", instance,
                        static_cast<int>(status), traits.size());
            for (const auto& trait : traits) {
                std::printf("%s: %s type=%s\n", instance, trait.name.c_str(),
                            trait.mediaType.c_str());
                names.emplace_back(trait.name.c_str());
            }
        });
        if (!result.isOk() || !listed || names.empty()) return 1;
        for (const auto& name : names) {
            bool created = false;
            auto creation = store->createInterface(name, [&](Status status, const auto& iface) {
                created = status == Status::OK && iface != nullptr;
                std::printf("%s: interface=%s status=%d valid=%d\n", instance,
                            name.c_str(), static_cast<int>(status), iface != nullptr);
            });
            if (!creation.isOk() || !created) return 1;
        }
    }
    std::puts("Both Dolby stores passed listComponents and createInterface.");
    return 0;
}
