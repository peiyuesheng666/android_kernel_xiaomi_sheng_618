// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.dolby;

import android.app.Application;
import android.content.Context;
import android.os.Build;
import android.util.Log;

/** API 1 bootstrap. New audio/UI types never appear in its method signatures. */
public final class CompatibilityApplication extends Application {
    private Object controller;

    public static int platformApi() {
        try { return Integer.parseInt(Build.VERSION.SDK); }
        catch (NumberFormatException invalid) { return 1; }
    }

    @Override public void onCreate() {
        super.onCreate();
        if (platformApi() < 35 || !"sheng".equals(Build.DEVICE)) return;
        try {
            controller = Class.forName("org.lineageos.sheng.dolby.AtmosApplication")
                    .getConstructor(new Class[]{Context.class}).newInstance(new Object[]{this});
        } catch (Exception failure) {
            Log.w("ShengDolby", "Audio controls unavailable", failure);
        } catch (LinkageError failure) {
            Log.w("ShengDolby", "Audio controls unavailable", failure);
        }
    }

    public Object controller() { return controller; }
}
