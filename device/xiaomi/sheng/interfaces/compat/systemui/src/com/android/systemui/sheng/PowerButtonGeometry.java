// SPDX-License-Identifier: Apache-2.0
package com.android.systemui.sheng;

/** Pure physical-to-logical mapping, in Surface rotation order (0, 90, 180, 270). */
public final class PowerButtonGeometry {
    private PowerButtonGeometry() {}

    public static float[] center(int rotation, float width, float height,
            float nativeY, float offscreenFraction) {
        if (rotation < 0 || rotation > 3 || width < 0 || height < 0) {
            throw new IllegalArgumentException("Invalid display geometry");
        }
        boolean sideways = rotation == 1 || rotation == 3;
        float nativeWidth = sideways ? height : width;
        float nativeHeight = sideways ? width : height;
        float y = Math.max(0, Math.min(nativeY, nativeHeight));
        float x = -nativeWidth * offscreenFraction;
        switch (rotation) {
            case 0: return new float[] {x, y};
            case 1: return new float[] {y, nativeWidth - x};
            case 2: return new float[] {nativeWidth - x, nativeHeight - y};
            default: return new float[] {nativeHeight - y, x};
        }
    }
}
