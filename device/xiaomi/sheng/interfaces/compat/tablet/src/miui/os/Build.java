// SPDX-License-Identifier: Apache-2.0
package miui.os;

/** Device-form-factor compatibility for apps using Xiaomi's tablet check. */
public final class Build {
    public static final boolean IS_TABLET =
            "tablet".equals(android.os.SystemProperties.get("ro.build.characteristics"));

    private Build() {}
}
