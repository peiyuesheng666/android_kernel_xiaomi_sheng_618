// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdint.h>

// Logical quad channels are FL, FR, LB, RB. The speaker MFC output media
// format must follow the tablet's physical TDM ordering, rather than a phone's
// stereo swap coefficient. Normal landscape order was verified on hardware.
inline void shengSpeakerPermutation(int degrees, uint8_t outputToInput[4]) {
    static constexpr uint8_t permutations[4][4] = {
        {3, 1, 2, 0},  // landscape
        {1, 0, 3, 2},  // reverse portrait
        {0, 2, 1, 3},  // reverse landscape
        {2, 3, 0, 1},  // portrait, charging port downward
    };
    // Absolute calibration: display rotation zero with the USB port on the
    // right uses [RB, FR, LB, FL]. Derive every other posture from that frame.
    const unsigned index = degrees >= 0 && degrees <= 270 && degrees % 90 == 0
            ? static_cast<unsigned>(degrees / 90) : 0;
    for (unsigned output = 0; output < 4; ++output)
        outputToInput[output] = permutations[index][output];
}
