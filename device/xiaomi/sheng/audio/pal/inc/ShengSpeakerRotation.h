// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdint.h>

// Logical quad channels are FL, FR, LB, RB. Physical TDM slots are ordered
// along each side: upper-left, lower-left, upper-right, lower-right at rotation
// zero. Return a bijection, preserving all four native Dolby channels and gain.
inline void shengSpeakerPermutation(int degrees, uint8_t outputToInput[4]) {
    static constexpr uint8_t permutations[4][4] = {
        {0, 2, 1, 3},  // landscape
        {2, 3, 0, 1},  // portrait
        {3, 1, 2, 0},  // reverse landscape
        {1, 0, 3, 2},  // reverse portrait
    };
    const unsigned index = degrees >= 0 && degrees <= 270 && degrees % 90 == 0
            ? static_cast<unsigned>(degrees / 90) : 0;
    for (unsigned output = 0; output < 4; ++output)
        outputToInput[output] = permutations[index][output];
}
