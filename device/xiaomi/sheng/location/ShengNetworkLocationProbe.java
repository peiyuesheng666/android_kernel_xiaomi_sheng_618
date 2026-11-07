import android.app.ActivityThread;
import android.content.Context;
import android.location.Location;
import android.location.LocationManager;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import java.util.concurrent.atomic.AtomicBoolean;

/** One bounded real network-provider request; never prints position identifiers. */
public final class ShengNetworkLocationProbe {
    public static void main(String[] args) {
        final int timeoutMs;
        try {
            timeoutMs = args.length == 0 ? 60000 : Math.max(1000, Math.min(60000, Integer.parseInt(args[0])));
        } catch (NumberFormatException ignored) {
            System.out.println("ERROR invalid_duration");
            return;
        }
        Looper.prepareMainLooper();
        Context context = ActivityThread.systemMain().getSystemContext();
        LocationManager manager = context.getSystemService(LocationManager.class);
        if (manager == null || !manager.getAllProviders().contains(LocationManager.NETWORK_PROVIDER)) {
            System.out.println("NETWORK unavailable");
            return;
        }
        try {
            if (!manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                System.out.println("NETWORK disabled");
                return;
            }
        } catch (SecurityException ignored) {
            System.out.println("ERROR provider_permission_denied");
            return;
        }
        Handler handler = new Handler(Looper.getMainLooper());
        CancellationSignal cancellation = new CancellationSignal();
        AtomicBoolean complete = new AtomicBoolean(false);
        long started = SystemClock.elapsedRealtime();
        Runnable timeout = () -> {
            if (complete.compareAndSet(false, true)) {
                cancellation.cancel();
                System.out.println("NETWORK timeout elapsedMs=" + (SystemClock.elapsedRealtime() - started));
                System.exit(2);
            }
        };
        handler.postDelayed(timeout, timeoutMs);
        System.out.println("NETWORK request provider=network timeoutMs=" + timeoutMs);
        try {
            manager.getCurrentLocation(LocationManager.NETWORK_PROVIDER, cancellation,
                command -> handler.post(command), location -> {
                    if (!complete.compareAndSet(false, true)) return;
                    handler.removeCallbacks(timeout);
                    cancellation.cancel();
                    if (location == null) {
                        System.out.println("NETWORK no_fix elapsedMs=" + (SystemClock.elapsedRealtime() - started));
                        System.exit(2);
                    }
                    long ageMs = (SystemClock.elapsedRealtimeNanos() - location.getElapsedRealtimeNanos()) / 1000000L;
                    System.out.println("NETWORK fix provider=" + location.getProvider()
                        + " ageMs=" + ageMs
                        + " accuracyM=" + (location.hasAccuracy() ? location.getAccuracy() : "unknown")
                        + " mock=" + location.isMock()
                        + " elapsedMs=" + (SystemClock.elapsedRealtime() - started));
                    System.exit(location.isMock() ? 3 : 0);
                });
        } catch (SecurityException ignored) {
            handler.removeCallbacks(timeout);
            cancellation.cancel();
            System.out.println("ERROR location_permission_denied");
            return;
        } catch (IllegalArgumentException ignored) {
            handler.removeCallbacks(timeout);
            cancellation.cancel();
            System.out.println("NETWORK unavailable");
            return;
        }
        Looper.loop();
    }
}
