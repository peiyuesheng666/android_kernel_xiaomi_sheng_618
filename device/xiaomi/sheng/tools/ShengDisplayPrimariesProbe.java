/* SPDX-License-Identifier: Apache-2.0 */
import android.os.IBinder;
import android.os.Parcel;
import android.os.ServiceManager;
import java.util.Locale;

/** Read-only physical-display/XYZ query; no pixels, mode writes or sensor activation. */
public final class ShengDisplayPrimariesProbe {
    // Checked against the pinned generated BnSurfaceComposer.h (FIRST_CALL + 5/6/14).
    private static Parcel query(IBinder service, int code, Long id, IBinder token)
            throws Exception {
        Parcel request = Parcel.obtain();
        Parcel reply = Parcel.obtain();
        try {
            request.writeInterfaceToken("android.gui.ISurfaceComposer");
            if (id != null) request.writeLong(id);
            if (token != null) request.writeStrongBinder(token);
            if (!service.transact(code, request, reply, 0)) {
                throw new IllegalStateException("Unsupported read-only query " + code);
            }
            reply.readException();
            return reply;
        } catch (Exception failure) {
            reply.recycle();
            throw failure;
        } finally {
            request.recycle();
        }
    }

    public static void main(String[] args) throws Exception {
        IBinder service = ServiceManager.checkService("SurfaceFlingerAIDL");
        if (service == null) throw new IllegalStateException("SurfaceFlingerAIDL absent");
        Parcel idsReply = query(service, 6, null, null);
        long[] ids;
        try { ids = idsReply.createLongArray(); } finally { idsReply.recycle(); }
        if (ids == null || ids.length == 0 || ids.length > 16) {
            throw new IllegalStateException("Unexpected physical-display count");
        }
        for (long id : ids) {
            Parcel tokenReply = query(service, 7, id, null);
            IBinder token;
            try { token = tokenReply.readStrongBinder(); } finally { tokenReply.recycle(); }
            if (token == null) throw new IllegalStateException("Physical display token absent");
            Parcel reply = query(service, 15, null, token);
            try {
                System.out.println("DISPLAY " + id + " XYZ_REPLY_BYTES=" + reply.dataAvail());
                // Preserve the size/presence words as well as exact IEEE754 components.
                while (reply.dataAvail() >= 4) {
                    int bits = reply.readInt();
                    System.out.printf(Locale.ROOT, "%08x %.9g%n", bits,
                            Float.intBitsToFloat(bits));
                }
                if (reply.dataAvail() != 0) throw new IllegalStateException("Unaligned XYZ reply");
            } finally { reply.recycle(); }
        }
    }
}
