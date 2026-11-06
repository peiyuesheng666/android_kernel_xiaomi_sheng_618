// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.dolby;

import android.media.audiofx.AudioEffect;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/** Stock DMS protocol through the HAL's existing protected AudioEffect bridge. */
final class StockDms {
    static final int IEQ = 104, DIALOG = 105, GEQ = 106, DIALOG_AMOUNT = 108, GAINS = 110;
    private static void send(AudioEffect effect, int opcode, int... values) {
        ByteBuffer bytes = ByteBuffer.allocate(8 + values.length * 4)
                .order(ByteOrder.LITTLE_ENDIAN).putInt(opcode << 24).putInt(0);
        for (int value : values) bytes.putInt(value);
        int status = effect.setParameter(5, bytes.array());
        if (status != AudioEffect.SUCCESS)
            throw new IllegalStateException("DMS command " + opcode + " returned " + status);
    }
    private static int[] read(AudioEffect effect, int opcode, int profile, int parameter, int count) {
        // Native getter packs bits 24/16/8 into opcode/parameter/profile.
        // Reserve room for its 12-byte request even for scalar replies.
        byte[] data = new byte[128];
        int key = (opcode << 24) | (parameter << 16) | (profile << 8) | 5;
        int status = effect.getParameter(key, data);
        if (status < count * 4) throw new IllegalStateException("DMS query returned " + status);
        ByteBuffer bytes = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN);
        int[] result = new int[count];
        for (int i = 0; i < count; i++) result[i] = bytes.getInt();
        return result;
    }
    static void setEnabled(AudioEffect effect, boolean enabled) { send(effect, 0, enabled ? 1 : 0); }
    static boolean isEnabled(AudioEffect effect) { return read(effect, 0, 0, 0, 1)[0] != 0; }
    static int getProfile(AudioEffect effect) { return read(effect, 10, 0, 0, 1)[0]; }
    static void setProfile(AudioEffect effect, int profile) { send(effect, 10, profile); }
    static void resetProfile(AudioEffect effect, int profile) { send(effect, 12, profile); }
    static int[] getParameter(AudioEffect effect, int profile, int parameter) {
        return read(effect, 1, profile, parameter, parameter == GAINS ? 20 : 1);
    }
    static void setParameter(AudioEffect effect, int profile, int parameter, int... data) {
        if (parameter == GAINS) {
            if (data.length != 20) throw new IllegalArgumentException("GEQ requires 20 bands");
            for (int value : data) if (value < -384 || value > 384)
                throw new IllegalArgumentException("GEQ limit is +/-6 dB");
        } else if (data.length != 1) throw new IllegalArgumentException("Scalar parameter required");
        int[] values = new int[2 + data.length];
        values[0] = profile; values[1] = parameter;
        System.arraycopy(data, 0, values, 2, data.length);
        send(effect, 1, values);
    }
}
