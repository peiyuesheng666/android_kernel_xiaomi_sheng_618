import android.content.res.AssetManager;
import android.content.res.Configuration;
import android.content.res.Resources;
import android.util.DisplayMetrics;
import java.lang.reflect.Method;
import java.util.Locale;

/** Resolve a candidate APK's own padding without changing the device configuration. */
public final class ShengSystemUiPaddingProbe {
    private static final String PACKAGE = "org.lineageos.systemuioverlay.xiaomi.sheng";
    private static final int[] DENSITIES = {280, 320, 360, 400, 466, 532, 600};

    public static void main(String[] args) {
        if (args.length != 1) {
            System.out.println("ERROR usage=ShengSystemUiPaddingProbe candidate.apk");
            System.exit(2);
        }
        AssetManager assets = null;
        int result = 2;
        try {
            assets = AssetManager.class.getDeclaredConstructor().newInstance();
            Method addPath = AssetManager.class.getDeclaredMethod("addAssetPath", String.class);
            if (((Integer) addPath.invoke(assets, args[0])) == 0) {
                throw new IllegalArgumentException("asset_path_rejected");
            }
            DisplayMetrics metrics = metrics(3048, 2032, 400);
            Resources resources = new Resources(assets, metrics,
                    configuration(3048, 2032, 400, Configuration.ORIENTATION_LANDSCAPE));
            int id = resources.getIdentifier("rounded_corner_content_padding", "dimen", PACKAGE);
            if (id == 0) throw new IllegalArgumentException("candidate_dimension_missing");
            int failures = 0;
            int cases = 0;
            for (int density : DENSITIES) {
                for (boolean portrait : new boolean[] {false, true}) {
                    int width = portrait ? 2032 : 3048;
                    int height = portrait ? 3048 : 2032;
                    int physicalOrientation = portrait
                            ? Configuration.ORIENTATION_PORTRAIT
                            : Configuration.ORIENTATION_LANDSCAPE;
                    for (boolean forceOpposite : new boolean[] {false, true}) {
                        int orientation = forceOpposite
                                ? (portrait ? Configuration.ORIENTATION_LANDSCAPE
                                            : Configuration.ORIENTATION_PORTRAIT)
                                : physicalOrientation;
                        Configuration config = configuration(width, height, density, orientation);
                        resources.updateConfiguration(config, metrics(width, height, density));
                        int px = resources.getDimensionPixelSize(id);
                        int expected = config.smallestScreenWidthDp < 600 ? 45 : portrait ? 40 : 45;
                        boolean pass = px == expected;
                        if (!pass) failures++;
                        cases++;
                        System.out.println((pass ? "PASS" : "FAIL")
                                + " density=" + density + " physical=" + width + "x" + height
                                + " sw=" + config.smallestScreenWidthDp
                                + " w=" + config.screenWidthDp + " h=" + config.screenHeightDp
                                + " orientation=" + (orientation == Configuration.ORIENTATION_PORTRAIT
                                        ? "port" : "land")
                                + " forced=" + forceOpposite + " px=" + px + " expected=" + expected);
                    }
                }
            }
            System.out.println("RESULT cases=" + cases + " failures=" + failures);
            result = failures == 0 ? 0 : 1;
        } catch (ReflectiveOperationException | RuntimeException | LinkageError failure) {
            // Hidden API refusal is a diagnostic failure; do not change runtime policy.
            System.out.println("ERROR asset_or_resource_resolution=" + failure.getClass().getSimpleName());
        } finally {
            if (assets != null) assets.close();
        }
        System.exit(result);
    }

    private static DisplayMetrics metrics(int width, int height, int densityDpi) {
        DisplayMetrics metrics = new DisplayMetrics();
        metrics.setToDefaults();
        metrics.widthPixels = width;
        metrics.heightPixels = height;
        metrics.densityDpi = densityDpi;
        metrics.density = densityDpi / 160f;
        metrics.scaledDensity = metrics.density;
        metrics.xdpi = densityDpi;
        metrics.ydpi = densityDpi;
        // Resources applies CompatibilityInfo even to this standalone asset.
        metrics.noncompatWidthPixels = width;
        metrics.noncompatHeightPixels = height;
        metrics.noncompatDensityDpi = densityDpi;
        metrics.noncompatDensity = metrics.density;
        metrics.noncompatScaledDensity = metrics.scaledDensity;
        metrics.noncompatXdpi = densityDpi;
        metrics.noncompatYdpi = densityDpi;
        return metrics;
    }

    private static Configuration configuration(int width, int height, int densityDpi,
            int orientation) {
        Configuration config = new Configuration();
        config.setToDefaults();
        config.setLocale(Locale.SIMPLIFIED_CHINESE);
        config.fontScale = 1f;
        config.densityDpi = densityDpi;
        config.screenWidthDp = width * 160 / densityDpi;
        config.screenHeightDp = height * 160 / densityDpi;
        config.smallestScreenWidthDp = Math.min(config.screenWidthDp, config.screenHeightDp);
        config.orientation = orientation;
        config.touchscreen = Configuration.TOUCHSCREEN_FINGER;
        config.uiMode = Configuration.UI_MODE_TYPE_NORMAL | Configuration.UI_MODE_NIGHT_NO;
        config.screenLayout = Configuration.SCREENLAYOUT_LAYOUTDIR_LTR
                | (config.smallestScreenWidthDp >= 720 ? Configuration.SCREENLAYOUT_SIZE_XLARGE
                        : config.smallestScreenWidthDp >= 600 ? Configuration.SCREENLAYOUT_SIZE_LARGE
                                : Configuration.SCREENLAYOUT_SIZE_NORMAL);
        return config;
    }
}
