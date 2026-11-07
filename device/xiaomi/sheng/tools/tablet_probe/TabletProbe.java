// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.tabletprobe;

import android.app.Instrumentation;
import android.content.res.Configuration;
import android.os.Build;
import android.os.Bundle;
import android.util.DisplayMetrics;
import java.util.Locale;

/** Read-only checks from an ordinary application UID; no Activity or capture. */
public final class TabletProbe extends Instrumentation {
    /** Isolated app_process check; does not attach to or restart zygote. */
    public static void main(String[] args) {
        System.out.println("runtime_bootclasspath=" + System.getProperty("java.boot.class.path"));
        try {
            Class<?> compat = Class.forName("miui.os.Build");
            System.out.println("compat_is_tablet=" + compat.getField("IS_TABLET").getBoolean(null));
        } catch (Throwable error) { error.printStackTrace(); }
    }
    @Override public void onCreate(Bundle args) { super.onCreate(args); start(); }
    @Override public void onStart() {
        Bundle result = new Bundle();
        Configuration config = getTargetContext().getResources().getConfiguration();
        DisplayMetrics metrics = getTargetContext().getResources().getDisplayMetrics();
        result.putInt("uid", android.os.Process.myUid());
        result.putString("runtime_bootclasspath", System.getProperty("java.boot.class.path"));
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
        } catch (Throwable error) {
            result.putString("compat_error", android.util.Log.getStackTraceString(error));
        }
        result.putBoolean("miui_class_present", miuiClass);
        try {
            Class<?> props = Class.forName("android.os.SystemProperties");
            String characteristics = (String) props.getMethod("get", String.class).invoke(null, "ro.build.characteristics");
            result.putString("characteristics", characteristics);
            boolean xiaomi = "xiaomi".equalsIgnoreCase(Build.BRAND) || "redmi".equalsIgnoreCase(Build.BRAND);
            result.putBoolean("douyin_xiaomi_predicate", xiaomi && "tablet".equals(characteristics) && miuiClass);
        } catch (Throwable error) { result.putString("property_error", error.toString()); }
        try {
            android.content.Context provider = getTargetContext().createPackageContext(
                    "com.android.providers.settings", 0);
            int checked = 0;
            StringBuilder failures = new StringBuilder();
            for (String locale : provider.getAssets().getLocales()) {
                Configuration localeConfig = new Configuration(provider.getResources().getConfiguration());
                localeConfig.setLocale(Locale.forLanguageTag(locale));
                android.content.res.Resources resources =
                        provider.createConfigurationContext(localeConfig).getResources();
                for (String name : new String[] {"def_device_name_simple", "def_device_name"}) {
                    int id = resources.getIdentifier(name, "string", "com.android.providers.settings");
                    String formatted = resources.getString(id, "24018RPACC", "24018RPACC");
                    if (!"Xiaomi Pad 6S Pro 12.4".equals(formatted)) {
                        failures.append(locale).append('/').append(name).append('=').append(formatted).append(';');
                    }
                    checked++;
                }
            }
            result.putInt("default_name_locale_cases", checked);
            result.putString("default_name_failures", failures.toString());
            result.putBoolean("default_name_all_locales_valid", checked > 0 && failures.length() == 0);
        } catch (Throwable error) { result.putString("default_name_error", error.toString()); }
        finish(-1, result);
    }
}
