// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdint.h>

// The stock final MFC (tag DEVICE_PP_MSIIR, MID 0x07001015) is after the
// speaker-swap MFC and its following processing. Its output goes to the TDM
// endpoint with channel IDs 1/2/4/5. Rotating the earlier MFC is undone by
// this final stage. USB-right landscape was verified at the final stage.
constexpr uint32_t SHENG_FINAL_SPEAKER_MFC_TAG = 0xc000003d;
inline void shengSpeakerPermutation(int degrees, uint8_t outputToInput[4]) {
    static constexpr uint8_t permutations[4][4] = {
        {3, 1, 2, 0},  // landscape
        {2, 3, 0, 1},  // reverse portrait
        {0, 2, 1, 3},  // reverse landscape
        {1, 0, 3, 2},  // portrait, charging port downward
    };
    // Absolute calibration: display rotation zero with the USB port on the
    // right uses [5,2,4,1]. Derive every other posture from that frame.
    const unsigned index = degrees >= 0 && degrees <= 270 && degrees % 90 == 0
            ? static_cast<unsigned>(degrees / 90) : 0;
    for (unsigned output = 0; output < 4; ++output)
        outputToInput[output] = permutations[index][output];
}
