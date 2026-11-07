// SPDX-License-Identifier: Apache-2.0
// Bounded by the caller's timeout; does not register or replace a HAL service.
#include <C2Component.h>
#include <binder/ProcessState.h>
#include <hidl/HidlTransportSupport.h>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <fstream>
#include <sstream>
#include <string>
#include <dirent.h>
#include <unistd.h>

namespace android {
std::shared_ptr<C2ComponentStore> GetCodec2DolbyComponentStore();
}

static unsigned long long cpuTicks() {
    std::ifstream input("/proc/self/stat");
    std::string line, token;
    std::getline(input, line);
    const auto close = line.rfind(')');
    if (close == std::string::npos) std::abort();
    std::istringstream fields(line.substr(close + 2));
    unsigned long long ticks = 0;
    for (int field = 3; field <= 15; ++field) {
        if (!(fields >> token)) std::abort();
        if (field == 14 || field == 15) ticks += std::stoull(token);
    }
    return ticks;
}

static int threads() {
    auto* directory = opendir("/proc/self/task");
    if (!directory) std::abort();
    int count = 0;
    while (auto* entry = readdir(directory)) if (entry->d_name[0] != '.') ++count;
    closedir(directory);
    return count;
}

int main(int argc, char** argv) {
    if (argc != 3) return 2;
    const int count = std::atoi(argv[2]);
    if (count < 1 || count > 20) return 2;
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    android::ProcessState::initWithDriver("/dev/vndbinder");
    android::ProcessState::self()->startThreadPool();
    android::hardware::configureRpcThreadpool(2, false);
    auto store = android::GetCodec2DolbyComponentStore();
    if (!store) return 1;
    std::printf("threads-before=%d\n", threads());
    for (int i = 0; i < count; ++i) {
        std::shared_ptr<C2Component> component;
        std::printf("iteration=%d creating=%s\n", i, argv[1]);
        const auto created = store->createComponent(argv[1], &component);
        std::printf("iteration=%d created=%d valid=%d\n", i, created, component != nullptr);
        if (created != C2_OK || !component) return 1;
        // HIDL Component::initListener sets SimpleC2Component's weak self.
        // Without this step release skips onRelease and misses the real fault.
        const auto listener = component->setListener_vb({}, C2_MAY_BLOCK);
        std::printf("iteration=%d listener=%d\n", i, listener);
        if (listener != C2_OK) return 1;
        const auto released = component->release();
        std::printf("iteration=%d released=%d\n", i, released);
        if (released != C2_OK) return 1;
        component.reset();
    }
    std::puts("lifecycle-complete; waiting 5 seconds for idle/thread inspection");
    const auto before = cpuTicks();
    sleep(5);
    const auto delta = cpuTicks() - before;
    std::printf("threads-after=%d idle-cpu-ticks=%llu ticks-per-second=%ld\n",
                threads(), delta, sysconf(_SC_CLK_TCK));
    return delta <= 5 ? 0 : 3;
}
