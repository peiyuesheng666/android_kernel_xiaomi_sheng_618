// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.tabletprobe;

import android.app.Instrumentation;
import android.content.res.Configuration;
import android.os.Build;
import android.os.Bundle;
import android.util.DisplayMetrics;

/** Read-only checks from an ordinary application UID; no Activity or capture. */
public final class TabletProbe extends Instrumentation {
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    @Override public void onStart() {
        Bundle result = new Bundle();
        Configuration config = getTargetContext().getResources().getConfiguration();
        DisplayMetrics metrics = getTargetContext().getResources().getDisplayMetrics();
        result.putInt("uid", android.os.Process.myUid());
        result.putInt("target_sdk", getTargetContext().getApplicationInfo().targetSdkVersion);
        result.putString("brand", Build.BRAND);
        result.putString("model", Build.MODEL);
        result.putInt("smallest_width_dp", config.smallestScreenWidthDp);
        result.putInt("screen_size", config.screenLayout & Configuration.SCREENLAYOUT_SIZE_MASK);
        result.putFloat("xdpi", metrics.xdpi);
        result.putFloat("ydpi", metrics.ydpi);
        boolean miuiClass = false;
        try {
            Class<?> compat = Class.forName("miui.os.Build");
            miuiClass = true;
            result.putBoolean("compat_is_tablet", compat.getField("IS_TABLET").getBoolean(null));
        } catch (Throwable error) { result.putString("compat_error", error.toString()); }
        result.putBoolean("miui_class_present", miuiClass);
        try {
            Class<?> props = Class.forName("android.os.SystemProperties");
            String characteristics = (String) props.getMethod("get", String.class).invoke(null, "ro.build.characteristics");
            result.putString("characteristics", characteristics);
            boolean xiaomi = "xiaomi".equalsIgnoreCase(Build.BRAND) || "redmi".equalsIgnoreCase(Build.BRAND);
            result.putBoolean("douyin_xiaomi_predicate", xiaomi && "tablet".equals(characteristics) && miuiClass);
        } catch (Throwable error) { result.putString("property_error", error.toString()); }
        finish(-1, result);
    }
}
