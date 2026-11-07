import android.app.ActivityThread;
import android.content.Context;
import android.location.Address;
import android.location.Geocoder;
import android.location.Location;
import android.location.LocationManager;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.os.Process;
import android.os.SystemClock;
import android.system.ErrnoException;
import android.system.Os;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** Bounded real network, reverse-geocode and forward-geocode diagnostics. */
public final class ShengGeocoderProbe {
    private static final long TIMEOUT_MS = 60000;

    private final Context context;
    private final Handler handler;
    private final long deadline;
    private final CancellationSignal cancellation = new CancellationSignal();
    private final CountDownLatch done = new CountDownLatch(1);
    private final AtomicInteger exitCode = new AtomicInteger(-1);
    private volatile String stage = "network";
    // Stage transitions and this flag are confined to handler's thread.
    private boolean geocodeFailed;
    private Geocoder geocoder;

    private ShengGeocoderProbe(Context context, Handler handler, long deadline) {
        this.context = context;
        this.handler = handler;
        this.deadline = deadline;
    }

    public static void main(String[] args) {
        final long deadline = SystemClock.elapsedRealtime() + TIMEOUT_MS;
        HandlerThread worker = null;
        ShengGeocoderProbe probe = null;
        int result = 4;
        try {
            // SystemContext attributes requests to android, owned by UID 1000.
            if (Process.myUid() == 0) {
                Os.setgid(Process.SYSTEM_UID);
                Os.setuid(Process.SYSTEM_UID);
            }
            Looper.prepareMainLooper();
            Context context = ActivityThread.systemMain().getSystemContext();
            worker = new HandlerThread("sheng-geocoder-probe");
            worker.start();
            probe = new ShengGeocoderProbe(context, new Handler(worker.getLooper()), deadline);
            probe.handler.post(probe::requestNetwork);
            long remaining = Math.max(0, deadline - SystemClock.elapsedRealtime());
            if (!probe.done.await(remaining, TimeUnit.MILLISECONDS)) {
                probe.finish(2, true);
            }
            result = probe.exitCode.get();
        } catch (ErrnoException | InterruptedException | RuntimeException | LinkageError failure) {
            if (failure instanceof InterruptedException) Thread.currentThread().interrupt();
            System.out.println("ERROR stage=" + (probe == null ? "setup" : probe.stage));
        } finally {
            // Also runs on timeout, setup failure and unsuccessful geocoding.
            if (probe != null) {
                probe.handler.removeCallbacksAndMessages(null);
                try {
                    probe.cancellation.cancel();
                } catch (RuntimeException | LinkageError failure) {
                    System.out.println("ERROR stage=cleanup");
                    result = 4;
                }
            }
            if (worker != null) worker.quitSafely();
        }
        System.exit(result);
    }

    private boolean active(String expectedStage) {
        if (exitCode.get() != -1 || !stage.equals(expectedStage)) return false;
        if (SystemClock.elapsedRealtime() >= deadline) {
            finish(2, true);
            return false;
        }
        return true;
    }

    private void requestNetwork() {
        if (!active("network")) return;
        handler.postDelayed(() -> finish(2, true),
                Math.max(0, deadline - SystemClock.elapsedRealtime()));
        try {
            LocationManager manager = context.getSystemService(LocationManager.class);
            if (manager == null
                    || !manager.getAllProviders().contains(LocationManager.NETWORK_PROVIDER)
                    || !manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                finish(1, true);
                return;
            }
            manager.getCurrentLocation(LocationManager.NETWORK_PROVIDER, cancellation,
                    command -> handler.post(command), this::onNetworkLocation);
        } catch (RuntimeException | LinkageError failure) {
            finish(1, true);
        }
    }

    private void onNetworkLocation(Location location) {
        if (!active("network")) return;
        if (location == null) {
            finish(1, true);
            return;
        }
        long ageMs = Math.max(0,
                (SystemClock.elapsedRealtimeNanos() - location.getElapsedRealtimeNanos()) / 1000000L);
        System.out.println("NETWORK ageMs=" + ageMs
                + " accuracyM=" + (location.hasAccuracy() ? location.getAccuracy() : "unknown")
                + " mock=" + location.isMock());
        if (location.isMock()) {
            finish(3, true);
            return;
        }
        stage = "reverse";
        try {
            if (!Geocoder.isPresent()) {
                finish(1, true);
                return;
            }
            geocoder = new Geocoder(context, Locale.SIMPLIFIED_CHINESE);
            if (!active("reverse")) return;
            geocoder.getFromLocation(location.getLatitude(), location.getLongitude(), 1,
                    listener("reverse"));
        } catch (RuntimeException | LinkageError failure) {
            onGeocodeError("reverse");
        }
    }

    private Geocoder.GeocodeListener listener(final String requestStage) {
        return new Geocoder.GeocodeListener() {
            @Override
            public void onGeocode(List<Address> addresses) {
                // Do not retain, stringify or log addresses received on Binder.
                final int count = addresses == null ? 0 : addresses.size();
                handler.post(() -> onGeocodeResults(requestStage, count));
            }

            @Override
            public void onError(String ignored) {
                // Backend messages may contain addresses; expose only the stage.
                handler.post(() -> onGeocodeError(requestStage));
            }
        };
    }

    private void onGeocodeResults(String requestStage, int count) {
        if (!active(requestStage)) return;
        System.out.println("GEOCODER stage=" + requestStage + " count=" + count);
        if (count == 0) geocodeFailed = true;
        advance(requestStage);
    }

    private void onGeocodeError(String requestStage) {
        if (!active(requestStage)) return;
        System.out.println("ERROR stage=" + requestStage);
        geocodeFailed = true;
        advance(requestStage);
    }

    private void advance(String requestStage) {
        if (requestStage.equals("forward")) {
            finish(geocodeFailed ? 1 : 0, false);
            return;
        }
        stage = "forward";
        if (!active("forward")) return;
        try {
            // Public place name only; never prints the request or returned addresses.
            geocoder.getFromLocationName("北京", 1, listener("forward"));
        } catch (RuntimeException | LinkageError failure) {
            onGeocodeError("forward");
        }
    }

    private void finish(int result, boolean error) {
        // The main-thread deadline and Handler completion may race. First wins.
        if (!exitCode.compareAndSet(-1, result)) return;
        if (error) System.out.println("ERROR stage=" + stage);
        done.countDown();
    }
}
