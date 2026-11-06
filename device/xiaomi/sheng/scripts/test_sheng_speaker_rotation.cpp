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
        // Opposite orientations must reverse both side pairs. The hardware
        // test supplies the absolute ordering; this catches channel loss or
        // an inconsistent opposite-angle mapping independently of that order.
        uint8_t opposite[4];
        shengSpeakerPermutation((degrees + 180) % 360, opposite);
        assert(opposite[0] == map[3] && opposite[1] == map[2]);
        assert(opposite[2] == map[1] && opposite[3] == map[0]);
    }
    puts("PASS four rotations preserve native quad channels and unity gain");
}
