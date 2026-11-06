// SPDX-License-Identifier: Apache-2.0
#include "ShengSpeakerRotation.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>

int main() {
    // Unique impulses must each reach one physical slot; speaker rotation must
    // never merge channels, duplicate energy, mute one side or add any gain.
    for (int degrees : {0, 90, 180, 270}) {
        uint8_t map[4];
        shengSpeakerPermutation(degrees, map);
        unsigned seen = 0;
        for (uint8_t input : map) {
            assert(input < 4 && !(seen & (1u << input)));
            seen |= 1u << input;
        }
        assert(seen == 15);
        // FL/LB impulses must share the physical left side in landscape;
        // inversion must move them together to the opposite physical side.
        if (degrees == 0) assert(map[0] % 2 == 0 && map[1] % 2 == 0);
        if (degrees == 180) assert(map[2] % 2 == 0 && map[3] % 2 == 0);
    }
    puts("PASS four rotations preserve native quad channels and unity gain");
}
