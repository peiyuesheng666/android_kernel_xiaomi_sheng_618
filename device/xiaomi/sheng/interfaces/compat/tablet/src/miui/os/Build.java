// SPDX-License-Identifier: Apache-2.0
package miui.os;

/** Device-form-factor compatibility for apps using Xiaomi's tablet check. */
public final class Build {
    public static final boolean IS_TABLET = isTablet();

    private static boolean isTablet() {
        // Keep compilation independent of a ROM's framework API stubs.
        try {
            Class<?> properties = Class.forName("android.os.SystemProperties");
            return "tablet".equals(properties.getMethod("get", String.class)
                    .invoke(null, "ro.build.characteristics"));
        } catch (ReflectiveOperationException | SecurityException ignored) {
            return false;
        }
    }

    private Build() {}
}
