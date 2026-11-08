// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.tabletprobe;

import android.content.res.AssetManager;
import android.content.res.Configuration;
import android.content.res.Resources;
import android.content.res.XmlResourceParser;
import android.util.DisplayMetrics;
import java.util.Locale;

/** Reads a temporary idmap in an isolated process, without installing an overlay. */
public final class ResourceProbe {
    public static void main(String[] args) throws Exception {
        if (args.length < 3 || args.length > 4) throw new IllegalArgumentException("package target-apk idmap [locale]");
        Class<?> apk = Class.forName("android.content.res.ApkAssets");
        Class<?> builderClass = Class.forName("android.content.res.AssetManager$Builder");
        Object builder = builderClass.getConstructor().newInstance();
        java.lang.reflect.Method add = builderClass.getMethod("addApkAssets", apk);
        if ("com.android.settings".equals(args[0])) {
            add.invoke(builder, apk.getMethod("loadFromPath", String.class).invoke(
                    null, "/system/framework/org.lineageos.platform-res.apk"));
        }
        add.invoke(builder, apk.getMethod("loadFromPath", String.class).invoke(null, args[1]));
        add.invoke(builder, apk.getMethod("loadOverlayFromPath", String.class, int.class)
                .invoke(null, args[2], 0));
        AssetManager assets = (AssetManager) builderClass.getMethod("build").invoke(builder);
        DisplayMetrics metrics = new DisplayMetrics();
        metrics.setToDefaults();
        Configuration configuration = new Configuration();
        configuration.setToDefaults();
        Locale selectedLocale = args.length == 4 ? Locale.forLanguageTag(args[3]) : Locale.SIMPLIFIED_CHINESE;
        configuration.setLocale(selectedLocale);
        Resources resources = new Resources(assets, metrics, configuration);
        if ("com.android.settings".equals(args[0])) {
            int controller = resources.getIdentifier("controller", "attr", args[0]);
            Locale locale = selectedLocale;
            boolean chinese = "zh".equals(locale.getLanguage());
            String[] labels = resources.getStringArray(resources.getIdentifier(
                    "config_color_mode_options_strings", "array", args[0]));
            String[] expectedLabels = chinese ? new String[] {"自适应", "生动", "鲜艳"}
                    : new String[] {"Adaptive", "Vivid", "Saturated"};
            if (!java.util.Arrays.equals(labels, expectedLabels)) throw new AssertionError("Color labels " + locale + ": " + java.util.Arrays.toString(labels));
            int[] modes = resources.getIntArray(resources.getIdentifier(
                    "config_color_mode_options_values", "array", args[0]));
            if (!java.util.Arrays.equals(modes, new int[] {0, 2, 1})) throw new AssertionError("Color modes");
            for (String xml : new String[] {"my_device_info", "hardware_info"}) {
                XmlResourceParser parser = resources.getXml(resources.getIdentifier(xml, "xml", args[0]));
                int controllers = 0;
                boolean marketing = false;
                boolean number = false;
                boolean codename = false;
                while (parser.next() != XmlResourceParser.END_DOCUMENT) {
                    if (parser.getEventType() != XmlResourceParser.START_TAG) continue;
                    String key = parser.getAttributeValue("http://schemas.android.com/apk/res/android", "key");
                    for (int i = 0; i < parser.getAttributeCount(); i++) {
                        int reference = parser.getAttributeResourceValue(i, 0);
                        if (reference != 0) {
                            android.util.TypedValue value = new android.util.TypedValue();
                            resources.getValue(reference, value, true);
                        }
                    }
                    for (int i = 0; i < parser.getAttributeCount(); i++) {
                        if ("controller".equals(parser.getAttributeName(i))) {
                            if (parser.getAttributeNameResource(i) != controller) {
                                throw new AssertionError("Controller attribute was remapped");
                            }
                            controllers++;
                        }
                    }
                    if ("sheng_marketname".equals(key)) {
                        String title = parser.getAttributeValue("http://schemas.android.com/apk/res/android", "title");
                        String summary = parser.getAttributeValue("http://schemas.android.com/apk/res/android", "summary");
                        marketing = (chinese ? "型号名称" : "Model name").equals(title) && "Xiaomi Pad 6S Pro 12.4".equals(summary);
                    }
                    if ("device_model".equals(key) || "hardware_info_device_model".equals(key)) {
                        number = (chinese ? "型号编号" : "Model number").equals(parser.getAttributeValue(
                                "http://schemas.android.com/apk/res/android", "title"));
                    }
                    if ("sheng_codename".equals(key)) {
                        codename = (chinese ? "设备代号" : "Device codename").equals(
                                parser.getAttributeValue("http://schemas.android.com/apk/res/android", "title"))
                                && "sheng".equals(parser.getAttributeValue(
                                        "http://schemas.android.com/apk/res/android", "summary"));
                    }
                }
                parser.close();
                if (controllers != ("my_device_info".equals(xml) ? 10 : 4) || !marketing || !number || !codename) {
                    throw new AssertionError(xml + " controllers=" + controllers + " marketing=" + marketing + " number=" + number + " codename=" + codename);
                }
                System.out.println(locale + "/" + xml + ": controllers=" + controllers + ", name, number and codename labels valid");
            }
        } else {
            int cases = 0;
            for (String locale : assets.getLocales()) {
                configuration.setLocale(Locale.forLanguageTag(locale));
                resources.updateConfiguration(configuration, metrics);
                for (String name : new String[] {"def_device_name", "def_device_name_simple"}) {
                    String value = resources.getString(resources.getIdentifier(name, "string", args[0]),
                            "24018RPACC", "24018RPACC");
                    if (!"Xiaomi Pad 6S Pro 12.4".equals(value)) {
                        throw new AssertionError(locale + "/" + name + "=" + value);
                    }
                    cases++;
                }
            }
            System.out.println("default_device_name_locale_cases=" + cases);
        }
    }
}
