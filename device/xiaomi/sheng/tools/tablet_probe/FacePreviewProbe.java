// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.tabletprobe;

import android.content.res.AssetManager;
import android.content.res.Configuration;
import android.content.res.Resources;
import android.util.DisplayMetrics;

/** Resolves a candidate idmap without installing it or requesting enrollment. */
public final class FacePreviewProbe {
    public static void main(String[] args) throws Exception {
        ResourceProbe.main(args); // Also preserve identity and color resources.
        Class<?> apk = Class.forName("android.content.res.ApkAssets");
        Class<?> builderClass = Class.forName("android.content.res.AssetManager$Builder");
        Object builder = builderClass.getConstructor().newInstance();
        java.lang.reflect.Method add = builderClass.getMethod("addApkAssets", apk);
        add.invoke(builder, apk.getMethod("loadFromPath", String.class).invoke(
                null, "/system/framework/org.lineageos.platform-res.apk"));
        add.invoke(builder, apk.getMethod("loadFromPath", String.class).invoke(null, args[1]));
        add.invoke(builder, apk.getMethod("loadOverlayFromPath", String.class, int.class)
                .invoke(null, args[2], 0));
        AssetManager assets = (AssetManager) builderClass.getMethod("build").invoke(builder);
        DisplayMetrics metrics = new DisplayMetrics();
        metrics.setToDefaults();
        Configuration config = new Configuration();
        config.setToDefaults();
        Resources resources = new Resources(assets, metrics, config);
        boolean ownsCamera = resources.getBoolean(resources.getIdentifier(
                "config_face_enroll_hal_owns_camera", "bool", args[0]));
        int width = resources.getInteger(resources.getIdentifier("face_preview_width", "integer", args[0]));
        int height = resources.getInteger(resources.getIdentifier("face_preview_height", "integer", args[0]));
        if (!ownsCamera || width != 640 || height != 480) {
            throw new AssertionError("Face preview: " + ownsCamera + ", " + width + "x" + height);
        }
        System.out.println("Face preview: HAL owns camera, " + width + "x" + height);
    }
}
