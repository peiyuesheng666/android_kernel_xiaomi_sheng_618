import java.lang.reflect.Method;

/** Read-only DMS 2.0 queries verified against the stock HIDL proxy. */
public final class ShengDmsStateProbe {
    private static final String DMS = "vendor.dolby.hardware.dms@2.0::IDms";
    private static final Class<?> PARCEL;
    private static final Method TRANSACT;
    private static final Object BINDER;
    static {
        try {
            PARCEL = Class.forName("android.os.HwParcel");
            Class<?> hwBinder = Class.forName("android.os.HwBinder");
            BINDER = hwBinder.getMethod("getService", String.class, String.class)
                    .invoke(null, DMS, "default");
            TRANSACT = Class.forName("android.os.IHwBinder").getMethod(
                    "transact", int.class, PARCEL, PARCEL, int.class);
        } catch (Exception error) { throw new RuntimeException(error); }
    }
    private static long getInt(String name) throws Exception {
        int key = 0;
        for (int i = 0; i < 4; i++) key = (key << 8) | name.charAt(i);
        Object request = PARCEL.getConstructor().newInstance();
        Object reply = PARCEL.getConstructor().newInstance();
        try {
            PARCEL.getMethod("writeInterfaceToken", String.class).invoke(request, DMS);
            PARCEL.getMethod("writeInt32", int.class).invoke(request, key);
            TRANSACT.invoke(BINDER, 20, request, reply, 0);
            PARCEL.getMethod("verifySuccess").invoke(reply);
            return (Long) PARCEL.getMethod("readInt64").invoke(reply);
        } finally {
            PARCEL.getMethod("releaseTemporaryStorage").invoke(request);
            PARCEL.getMethod("release").invoke(reply);
        }
    }
    public static void main(String[] args) throws Exception {
        if (args.length == 2 && "tuning-select".equals(args[0])) {
            Object request = PARCEL.getConstructor().newInstance();
            Object reply = PARCEL.getConstructor().newInstance();
            try {
                java.util.ArrayList<Byte> name = new java.util.ArrayList<>();
                for (byte value : (args[1] + '\0').getBytes("UTF-8")) name.add(value);
                PARCEL.getMethod("writeInterfaceToken", String.class).invoke(request, DMS);
                PARCEL.getMethod("writeInt32", int.class).invoke(request, 0);
                PARCEL.getMethod("writeInt8Vector", java.util.ArrayList.class).invoke(request, name);
                // Verified from the stock BpHwDms: port, byte vector, transaction 14.
                TRANSACT.invoke(BINDER, 14, request, reply, 0);
                PARCEL.getMethod("verifySuccess").invoke(reply);
                System.out.println("SPEAKER_TUNING_SELECTED=" + args[1]);
            } finally {
                PARCEL.getMethod("releaseTemporaryStorage").invoke(request);
                PARCEL.getMethod("release").invoke(reply);
            }
        }
        if (args.length > 0 && "profile-reset".equals(args[0])) {
            Object request = PARCEL.getConstructor().newInstance();
            Object reply = PARCEL.getConstructor().newInstance();
            java.util.ArrayList<Byte> command = new java.util.ArrayList<>();
            for (byte b : new byte[]{0,0,0,10,0,0,0,0,0,0,0,0}) command.add(b);
            PARCEL.getMethod("writeInterfaceToken", String.class).invoke(request, DMS);
            PARCEL.getMethod("writeInt8Vector", java.util.ArrayList.class).invoke(request, command);
            TRANSACT.invoke(BINDER, 8, request, reply, 0);
            PARCEL.getMethod("verifySuccess").invoke(reply);
            System.out.println("RESET_PROFILE=" + PARCEL.getMethod("readInt32").invoke(reply));
            PARCEL.getMethod("releaseTemporaryStorage").invoke(request);
            PARCEL.getMethod("release").invoke(reply);
        }
        if (args.length > 0 && "effect-bridge-test".equals(args[0])) {
            android.media.audiofx.AudioEffect effect = new android.media.audiofx.AudioEffect(
                java.util.UUID.fromString("ec7178ec-e5e1-4432-a3f4-4657e6795210"),
                java.util.UUID.fromString("9d4921da-8225-4f29-aefa-39537a04bcaa"), 20, 0);
            try {
                for (int profile : new int[]{1, 2, 0}) {
                    byte[] command = java.nio.ByteBuffer.allocate(12)
                        .order(java.nio.ByteOrder.LITTLE_ENDIAN).putInt(10 << 24).putInt(0).putInt(profile).array();
                    System.out.println("PROFILE_SET=" + profile + " STATUS=" + effect.setParameter(5, command));
                    Thread.sleep(300);
                    byte[] read = new byte[12];
                    System.out.println("PROFILE_READ_STATUS=" + effect.getParameter(0x0a000005, read));
                    System.out.println("PROFILE_READ_BYTES=" + java.util.Arrays.toString(read));
                }
                for (int param : new int[]{104,105,106,107,108,110}) {
                    byte[] read = new byte[128];
                    int code = 0x01000005 | (param << 16) | (3 << 8);
                    System.out.println("PARAM=" + param + " READ_STATUS=" + effect.getParameter(code, read)
                        + " BYTES=" + java.util.Arrays.toString(java.util.Arrays.copyOf(read, param == 110 ? 80 : 12)));
                }
                byte[] command = java.nio.ByteBuffer.allocate(20)
                    .order(java.nio.ByteOrder.LITTLE_ENDIAN).putInt(1 << 24).putInt(0).putInt(3).putInt(108).putInt(5).array();
                System.out.println("DIALOG_SET_STATUS=" + effect.setParameter(5, command));
                Thread.sleep(300);
                byte[] read = new byte[128];
                System.out.println("DIALOG_GET_STATUS=" + effect.getParameter(0x016c0305, read));
                System.out.println("DIALOG_GET_BYTES=" + java.util.Arrays.toString(java.util.Arrays.copyOf(read, 12)));
            } finally { effect.release(); }
        }
        if (args.length > 0 && "dms-switch-test".equals(args[0])) {
            for (int value : new int[]{0, 1}) {
                Object request = PARCEL.getConstructor().newInstance();
                Object reply = PARCEL.getConstructor().newInstance();
                java.util.ArrayList<Byte> command = new java.util.ArrayList<>();
                for (byte b : java.nio.ByteBuffer.allocate(12).order(java.nio.ByteOrder.LITTLE_ENDIAN)
                    .putInt(0).putInt(0).putInt(value).array()) command.add(b);
                PARCEL.getMethod("writeInterfaceToken", String.class).invoke(request, DMS);
                PARCEL.getMethod("writeInt8Vector", java.util.ArrayList.class).invoke(request, command);
                TRANSACT.invoke(BINDER, 8, request, reply, 0);
                PARCEL.getMethod("verifySuccess").invoke(reply);
                System.out.println("DIRECT_SET_" + value + "=" + PARCEL.getMethod("readInt32").invoke(reply));
                PARCEL.getMethod("releaseTemporaryStorage").invoke(request);
                PARCEL.getMethod("release").invoke(reply);
                Thread.sleep(2000);
                System.out.println("DIRECT_DAPO_" + value + "=" + getInt("DAPO"));
            }
        }
        if (args.length > 0 && "profile-read".equals(args[0])) {
            Object request = PARCEL.getConstructor().newInstance();
            Object reply = PARCEL.getConstructor().newInstance();
            java.util.ArrayList<Byte> command = new java.util.ArrayList<>();
            for (byte value : new byte[]{0,0,0,10,0,0,0,0,0,0,0,0}) command.add(value);
            PARCEL.getMethod("writeInterfaceToken", String.class).invoke(request, DMS);
            PARCEL.getMethod("writeInt8Vector", java.util.ArrayList.class).invoke(request, command);
            TRANSACT.invoke(BINDER, 9, request, reply, 0);
            PARCEL.getMethod("verifySuccess").invoke(reply);
            System.out.println("PROFILE_STATUS=" + PARCEL.getMethod("readInt32").invoke(reply));
            System.out.println("PROFILE_BYTES=" + PARCEL.getMethod("readInt8Vector").invoke(reply));
            PARCEL.getMethod("releaseTemporaryStorage").invoke(request);
            PARCEL.getMethod("release").invoke(reply);
        }
        if (args.length > 0 && "effect-switch-test".equals(args[0])) {
            android.media.audiofx.AudioEffect effect = new android.media.audiofx.AudioEffect(
                java.util.UUID.fromString("ec7178ec-e5e1-4432-a3f4-4657e6795210"),
                java.util.UUID.fromString("9d4921da-8225-4f29-aefa-39537a04bcaa"), 20, 0);
            try {
                System.out.println("CONTROL=" + effect.hasControl());
                for (int value : new int[]{0, 1}) {
                    byte[] command = java.nio.ByteBuffer.allocate(12)
                        .order(java.nio.ByteOrder.LITTLE_ENDIAN).putInt(0).putInt(0).putInt(value).array();
                    System.out.println("SET_" + value + "=" + effect.setParameter(5, command));
                    Thread.sleep(2000);
                    System.out.println("DAPO_" + value + "=" + getInt("DAPO"));
                }
            } finally { effect.release(); }
        }
        for (String key : new String[]{"DAPO", "ADEV", "CHCT", "SPKP", "SPKM", "SPAA"})
            System.out.println(key + "=" + getInt(key));
        for (int port = 0; port < 7; port++) {
        Object request = PARCEL.getConstructor().newInstance();
        Object reply = PARCEL.getConstructor().newInstance();
        try {
            PARCEL.getMethod("writeInterfaceToken", String.class).invoke(request, DMS);
            PARCEL.getMethod("writeInt32", int.class).invoke(request, port); // dolby::Port, not Android device mask
            TRANSACT.invoke(BINDER, 13, request, reply, 0); // getSelectedTuningDevice
            PARCEL.getMethod("verifySuccess").invoke(reply);
            java.util.ArrayList<?> bytes = (java.util.ArrayList<?>)
                    PARCEL.getMethod("readInt8Vector").invoke(reply);
            byte[] text = new byte[bytes.size()];
            for (int i = 0; i < text.length; i++) text[i] = (Byte) bytes.get(i);
            System.out.println("PORT_" + port + "_TUNING=" + new String(text, "UTF-8").replace('\0', ' '));
        } finally {
            PARCEL.getMethod("releaseTemporaryStorage").invoke(request);
            PARCEL.getMethod("release").invoke(reply);
        }
        }
        System.exit(0);
    }
}
