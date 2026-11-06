// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.dolby;

import android.media.audiofx.AudioEffect;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/** Use the stock DAP effect's verified DMS control bridge. */
final class StockDms {
    static void setEnabled(AudioEffect effect, boolean enabled) {
        // Command 0 (DsOn), reserved reply word, scalar value. Native code
        // reads the value at byte 8 and persists it via saveDsState().
        byte[] command = ByteBuffer.allocate(12).order(ByteOrder.LITTLE_ENDIAN)
                .putInt(0).putInt(0).putInt(enabled ? 1 : 0).array();
        // Native DapEffectContext::setParam(5) forwards this buffer to
        // IDms::setDapParam. The HAL already has the required service access.
        int status = effect.setParameter(5, command);
        if (status != AudioEffect.SUCCESS)
            throw new IllegalStateException("Stock DMS switch returned " + status);
    }
}
