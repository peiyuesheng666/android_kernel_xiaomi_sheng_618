// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.dolby;

import android.os.HwBinder;
import android.os.HwParcel;
import android.os.IHwBinder;
import android.os.RemoteException;
import android.util.Log;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;

/** Select the OEM quad speaker tuning through the stock DMS 2.0 interface. */
final class SpeakerTuning {
    private static final String DMS = "vendor.dolby.hardware.dms@2.0::IDms";
    private static String selected(IHwBinder service) throws RemoteException {
        HwParcel request = new HwParcel(), reply = new HwParcel();
        try {
            request.writeInterfaceToken(DMS);
            request.writeInt32(0); // internal_speaker port, not an Android device mask
            service.transact(13, request, reply, 0);
            reply.verifySuccess();
            ArrayList<Byte> vector = reply.readInt8Vector();
            byte[] bytes = new byte[vector.size()];
            for (int i = 0; i < bytes.length; i++) bytes[i] = vector.get(i);
            return new String(bytes, StandardCharsets.UTF_8).replace("\0", "");
        } finally { request.releaseTemporaryStorage(); reply.release(); }
    }
    static void apply(boolean landscape) throws RemoteException {
        IHwBinder service = HwBinder.getService(DMS, "default");
        String name = landscape ? "speaker_landscape" : "speaker_portrait";
        if (name.equals(selected(service))) return;
        HwParcel request = new HwParcel(), reply = new HwParcel();
        try {
            request.writeInterfaceToken(DMS);
            request.writeInt32(0);
            ArrayList<Byte> bytes = new ArrayList<>();
            // Native DMS uses the vector's exact length to construct its name.
            for (byte value : name.getBytes(StandardCharsets.UTF_8)) bytes.add(value);
            request.writeInt8Vector(bytes);
            service.transact(14, request, reply, 0);
            reply.verifySuccess();
        } finally { request.releaseTemporaryStorage(); reply.release(); }
        if (!name.equals(selected(service)))
            throw new IllegalStateException("OEM speaker tuning was not selected: " + name);
        Log.i("ShengDolby", "Selected OEM four-channel tuning " + name);
    }
}
