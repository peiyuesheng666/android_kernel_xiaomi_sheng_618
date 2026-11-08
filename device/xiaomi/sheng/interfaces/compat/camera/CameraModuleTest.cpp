// SPDX-License-Identifier: Apache-2.0
// No camera is opened or loaded. Exercise only synthetic metadata and fake HAL callbacks.
#define SHENG_CAMERA_TEST
#include "CameraModule.cpp"
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <vector>

#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAILED line %d: %s\n", __LINE__, #x); std::abort(); } } while (0)

namespace {
camera_metadata_t* fixture;
camera_module_t fake{};
const hw_module_t* openedModule;
int fakeInfo(int id, camera_info* info) {
    if (id < 0) return -EINVAL;
    *info = {};
    info->orientation = 90;
    info->static_camera_characteristics = fixture;
    return 0;
}
int fakePhysical(int id, camera_metadata_t** metadata) {
    if (id < 0) return -EINVAL;
    *metadata = fixture;
    return 0;
}
int fakeOpen(const hw_module_t* module, const char*, hw_device_t**) {
    openedModule = module;
    return -EBUSY;
}
int fakeLegacy(const hw_module_t* module, const char*, uint32_t, hw_device_t**) {
    openedModule = module;
    return -EUSERS;
}

camera_metadata_t* makeMetadata(uint8_t facing, int32_t orientation) {
    auto* metadata = allocate_camera_metadata(4, 64);
    CHECK(metadata);
    int32_t sensitivity[2] = {50, 12800};
    CHECK(!add_camera_metadata_entry(metadata, ANDROID_LENS_FACING, &facing, 1));
    CHECK(!add_camera_metadata_entry(metadata, ANDROID_SENSOR_ORIENTATION, &orientation, 1));
    CHECK(!add_camera_metadata_entry(metadata, ANDROID_SENSOR_INFO_SENSITIVITY_RANGE, sensitivity, 2));
    return metadata;
}
int32_t angle(const camera_metadata_t* metadata) {
    camera_metadata_ro_entry_t entry{};
    CHECK(!find_camera_metadata_ro_entry(metadata, ANDROID_SENSOR_ORIENTATION, &entry));
    return entry.data.i32[0];
}
}

int main() {
    for (uint8_t facing : {ANDROID_LENS_FACING_BACK, ANDROID_LENS_FACING_FRONT, ANDROID_LENS_FACING_EXTERNAL}) {
        for (int32_t before : {0, 90, 180, 270}) {
            auto* metadata = makeMetadata(facing, before);
            const camera_metadata_t* output = nullptr;
            CHECK(!correctedMetadata(metadata, &output));
            int32_t expected = before;
            if ((facing == ANDROID_LENS_FACING_BACK && before == 90) ||
                (facing == ANDROID_LENS_FACING_FRONT && before == 270)) expected = 0;
            CHECK(angle(output) == expected);
            CHECK(angle(metadata) == before);
            CHECK(get_camera_metadata_entry_count(metadata) == get_camera_metadata_entry_count(output));
            for (size_t i = 0; i < get_camera_metadata_entry_count(metadata); ++i) {
                camera_metadata_ro_entry_t oldEntry{}, newEntry{};
                CHECK(!get_camera_metadata_ro_entry(metadata, i, &oldEntry));
                CHECK(!get_camera_metadata_ro_entry(output, i, &newEntry));
                CHECK(oldEntry.tag == newEntry.tag && oldEntry.type == newEntry.type && oldEntry.count == newEntry.count);
                if (oldEntry.tag != ANDROID_SENSOR_ORIENTATION)
                    CHECK(!std::memcmp(oldEntry.data.u8, newEntry.data.u8, oldEntry.count * camera_metadata_type_size[oldEntry.type]));
            }
            // Keep input pointers alive: OEM static metadata has provider lifetime.
        }
    }
    fixture = makeMetadata(ANDROID_LENS_FACING_BACK, 90);
    hw_module_methods_t fakeMethods{.open = fakeOpen};
    fake.common.methods = &fakeMethods;
    fake.get_camera_info = fakeInfo;
    fake.get_physical_camera_info = fakePhysical;
    fake.open_legacy = fakeLegacy;
    original = &fake;
    camera_info info{};
    CHECK(!getCameraInfo(0, &info));
    CHECK(info.orientation == 0 && angle(info.static_camera_characteristics) == 0);
    CHECK(getCameraInfo(-1, &info) == -EINVAL);
    camera_metadata_t* physical = nullptr;
    CHECK(!getPhysicalInfo(4, &physical));
    CHECK(physical == info.static_camera_characteristics);
    CHECK(getPhysicalInfo(-1, &physical) == -EINVAL);
    CHECK(methods.open(nullptr, "0", nullptr) == -EBUSY && openedModule == &fake.common);
    CHECK(openLegacy(nullptr, "0", 0, nullptr) == -EUSERS && openedModule == &fake.common);
    const camera_metadata_t* stable = info.static_camera_characteristics;
    std::vector<std::thread> threads;
    for (int i = 0; i < 16; ++i) threads.emplace_back([stable] {
        for (int j = 0; j < 100; ++j) {
            camera_info local{};
            CHECK(!getCameraInfo(0, &local));
            CHECK(local.static_camera_characteristics == stable && local.orientation == 0);
        }
    });
    for (auto& thread : threads) thread.join();
    CHECK(angle(fixture) == 90);
    const camera_metadata_t* nullOutput = fixture;
    CHECK(!correctedMetadata(nullptr, &nullOutput) && !nullOutput);
    std::puts("PASS: 12 orientation cases, immutable metadata, error/open forwarding, 1600 concurrent cache reads; no camera loaded/opened");
}
