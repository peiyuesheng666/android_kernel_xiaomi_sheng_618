// SPDX-License-Identifier: Apache-2.0
package com.android.systemui.sheng;

import android.content.Context;
import android.graphics.Point;
import android.view.Display;
import com.android.app.animation.Interpolators;
import com.android.systemui.statusbar.LightRevealScrim;

/** Device-specific button edge, preserving the upstream animation timing and oval. */
public final class PowerButtonEffect {
    private PowerButtonEffect() {}

    public static void apply(float amount, LightRevealScrim scrim, float nativeY) {
        float interpolated = Interpolators.FAST_OUT_SLOW_IN_REVERSE.getInterpolation(amount);
        float fade = Math.max(interpolated - 0.5f, 0f) / 0.5f;
        scrim.setRevealGradientEndColorAlpha(1f - fade);
        // The upstream optimizer removes interpolatedRevealAmount: it has no readers.
        // Do not call that removed setter from a separately compiled helper.
        Display display = scrim.getDisplay();
        int rotation = display == null ? 0 : display.getRotation();
        float width = scrim.getWidth(), height = scrim.getHeight();
        float[] center = PowerButtonGeometry.center(rotation, width, height, nativeY, 0.05f);
        boolean vertical = rotation == 0 || rotation == 2;
        float radiusX = width * (vertical ? 1.25f : 1f) * interpolated;
        float radiusY = height * (vertical ? 1f : 1.25f) * interpolated;
        scrim.setRevealGradientBounds(center[0] - radiusX, center[1] - radiusY,
                center[0] + radiusX, center[1] + radiusY);
    }

    @SuppressWarnings("deprecation")
    public static Point wakeOrigin(Context context) {
        Display display = context.getDisplay();
        Point size = new Point();
        int rotation = 0;
        if (display != null) {
            display.getRealSize(size);
            rotation = display.getRotation();
        } else {
            size.set(context.getResources().getDisplayMetrics().widthPixels,
                    context.getResources().getDisplayMetrics().heightPixels);
        }
        // R8 removes the R class from the final APK; resolve the retained resource by name.
        int resource = context.getResources().getIdentifier(
                "physical_power_button_center_screen_location_y", "dimen", "com.android.systemui");
        if (resource == 0) throw new IllegalStateException("Missing power button geometry resource");
        float nativeY = context.getResources().getDimension(resource);
        float[] center = PowerButtonGeometry.center(rotation, size.x, size.y, nativeY, 0f);
        return new Point(Math.round(center[0]), Math.round(center[1]));
    }
}
