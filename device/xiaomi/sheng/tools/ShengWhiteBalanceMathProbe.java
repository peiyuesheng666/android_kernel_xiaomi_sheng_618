/* SPDX-License-Identifier: Apache-2.0 */
import android.graphics.ColorSpace;
import java.util.Locale;

/** Pure color math: no sensors, display writes, pixels, camera or services. */
public final class ShengWhiteBalanceMathProbe {
    public static void main(String[] args) {
        float[] neutral = ColorSpace.cctToXyz(6500);
        System.out.printf(Locale.ROOT, "NEUTRAL_6500_XYZ %.9g %.9g %.9g%n",
                neutral[0], neutral[1], neutral[2]);
        float[] old = {0.9505f, 1.0f, 1.0891f};
        for (int cct : new int[]{5300, 5600, 6000, 6499, 6500, 6501, 8100}) {
            for (float[] reference : new float[][]{old, neutral}) {
                float[] matrix = ColorSpace.chromaticAdaptation(ColorSpace.Adaptation.BRADFORD,
                        reference, ColorSpace.cctToXyz(cct));
                System.out.printf(Locale.ROOT, "CCT %d reference=%s XYZ_ADAPT",
                        cct, reference == neutral ? "matched" : "D65");
                float error = 0;
                for (int i = 0; i < 9; ++i) {
                    System.out.printf(Locale.ROOT, " %.9g", matrix[i]);
                    error = Math.max(error, Math.abs(matrix[i] - (i % 4 == 0 ? 1f : 0f)));
                }
                System.out.printf(Locale.ROOT, " identity_error=%.9g%n", error);
                if (reference == neutral && cct == 6500 && error != 0) {
                    throw new AssertionError("Nominal CCT must meet the disabled identity exactly");
                }
            }
        }
    }
}
