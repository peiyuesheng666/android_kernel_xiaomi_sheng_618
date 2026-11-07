// SPDX-License-Identifier: Apache-2.0
import com.android.systemui.sheng.PowerButtonGeometry;

public final class PowerButtonGeometryTest {
    private static int checked;

    private static void close(float actual, float expected) {
        if (Math.abs(actual - expected) > 0.002f) {
            throw new AssertionError(actual + " != " + expected);
        }
        checked++;
    }

    public static void main(String[] args) {
        // Physical positions independently specified for the same left button
        // under the four display rotations; cover normal and zoomed view sizes.
        for (float scale : new float[] {0.5f, 1f, 1.5f, 2f}) {
            float w = 3048 * scale, h = 2032 * scale, y = 620 * scale;
            float[][] expected = {{0, y}, {y, w}, {w, h - y}, {h - y, 0}};
            for (int rotation = 0; rotation < 4; rotation++) {
                boolean sideways = rotation % 2 != 0;
                float width = sideways ? h : w, height = sideways ? w : h;
                float[] p = PowerButtonGeometry.center(rotation, width, height, y, 0);
                close(p[0], expected[rotation][0]);
                close(p[1], expected[rotation][1]);
                float[] off = PowerButtonGeometry.center(rotation, width, height, y, .05f);
                // The reveal oval starts outside the same physical edge.
                if (rotation == 0) { close(off[0], -.05f * w); close(off[1], p[1]); }
                if (rotation == 1) { close(off[0], p[0]); close(off[1], 1.05f * w); }
                if (rotation == 2) { close(off[0], 1.05f * w); close(off[1], p[1]); }
                if (rotation == 3) { close(off[0], p[0]); close(off[1], -.05f * w); }
            }
        }
        close(PowerButtonGeometry.center(0, 100, 200, -5, 0)[1], 0);
        close(PowerButtonGeometry.center(0, 100, 200, 205, 0)[1], 200);
        System.out.println("Power-button geometry assertions passed: " + checked);
    }
}
