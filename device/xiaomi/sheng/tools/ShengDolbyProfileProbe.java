// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.dolby;

import android.media.audiofx.AudioEffect;
import java.util.Arrays;
import java.util.UUID;

/** Queries the production bridge; --cycle temporarily selects and restores profiles. */
public final class ShengDolbyProfileProbe {
    private static void snapshot(AudioEffect effect, String label) {
        int profile = StockDms.getProfile(effect);
        System.out.println(label + " profile=" + profile + " enabled=" + StockDms.isEnabled(effect)
                + " control=" + effect.hasControl());
        for (int parameter : new int[]{104, 105, 106, 108, 110}) {
            System.out.println("PARAM profile=" + profile + " id=" + parameter + " value="
                    + Arrays.toString(StockDms.getParameter(effect, profile, parameter)));
        }
    }

    public static void main(String[] args) throws Exception {
        boolean cycle = args.length == 1 && "--cycle".equals(args[0]);
        if (args.length != 0 && !cycle) throw new IllegalArgumentException("Use --cycle or no arguments");
        AudioEffect effect = new AudioEffect(
                UUID.fromString("ec7178ec-e5e1-4432-a3f4-4657e6795210"),
                UUID.fromString("9d4921da-8225-4f29-aefa-39537a04bcaa"), cycle ? 20 : 0, 0);
        try {
            snapshot(effect, "BEFORE");
            if (cycle) {
                int original = StockDms.getProfile(effect);
                try {
                    for (int profile : new int[]{0, 1, 2, 3, 8}) {
                        StockDms.setProfile(effect, profile);
                        Thread.sleep(200);
                        snapshot(effect, "REQUEST=" + profile);
                        if (StockDms.getProfile(effect) != profile)
                            throw new IllegalStateException("Profile readback mismatch: " + profile);
                    }
                } finally {
                    StockDms.setProfile(effect, original);
                    Thread.sleep(200);
                    snapshot(effect, "RESTORED");
                    if (StockDms.getProfile(effect) != original)
                        throw new IllegalStateException("Original profile was not restored");
                }
            }
        } finally { effect.release(); }
        System.exit(0);
    }
}
