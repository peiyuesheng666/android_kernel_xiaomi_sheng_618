/* SPDX-License-Identifier: Apache-2.0 */
#pragma once

#include <cmath>
#include <cstdint>
#include <string_view>

namespace sheng {

// The private front sensor reports Kelvin in data[0], despite its incorrect
// declared maxRange. Match both event and sensor identity so metadata/flush,
// back-CCT and other sensor payloads never enter this filter.
inline bool RejectInvalidFrontCct(int32_t event_type, int32_t sensor_type,
                                  std::string_view string_type, bool wakeup, float kelvin) {
    constexpr int32_t kFrontCct = 33171088;
    if (event_type != kFrontCct || sensor_type != kFrontCct || wakeup ||
        string_type != "xiaomi.sensor.front_cct") {
        return false;
    }
    return !std::isfinite(kelvin) || kelvin <= 0.0f;
}

}  // namespace sheng
