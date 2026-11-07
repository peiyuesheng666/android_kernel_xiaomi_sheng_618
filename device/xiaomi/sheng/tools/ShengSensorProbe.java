import android.app.ActivityThread;
import android.content.Context;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.Handler;
import android.os.Looper;
import java.util.Arrays;
import java.util.HashMap;

/** Bounded read-only sampling of stock ALS/RGB/CCT paths. */
public final class ShengSensorProbe {
    public static void main(String[] args) {
        Looper.prepareMainLooper();
        Context context = ActivityThread.systemMain().getSystemContext();
        SensorManager manager = context.getSystemService(SensorManager.class);
        Handler handler = new Handler(Looper.getMainLooper());
        int durationMs = args.length > 0 ? Math.min(180000, Math.max(5000, Integer.parseInt(args[0]))) : 25000;
        HashMap<String, Integer> counts = new HashMap<>();
        HashMap<String, float[]> ranges = new HashMap<>();
        long started = android.os.SystemClock.elapsedRealtime();
        SensorEventListener listener = new SensorEventListener() {
            public void onAccuracyChanged(Sensor sensor, int accuracy) {
                System.out.println("ACCURACY " + sensor.getName() + "=" + accuracy);
            }
            public void onSensorChanged(SensorEvent event) {
                String key = event.sensor.getType() + ":" + event.sensor.isWakeUpSensor();
                int count = counts.getOrDefault(key, 0) + 1;
                counts.put(key, count);
                float[] range = ranges.computeIfAbsent(key, k -> new float[]{Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY});
                if (event.values.length > 0 && Float.isFinite(event.values[0])) {
                    range[0] = Math.min(range[0], event.values[0]);
                    range[1] = Math.max(range[1], event.values[0]);
                }
                if (count <= 6 || count % 20 == 0 || event.sensor.getType() == 5)
                    System.out.println("SAMPLE elapsedMs=" + (android.os.SystemClock.elapsedRealtime() - started)
                        + " ageMs=" + (android.os.SystemClock.elapsedRealtimeNanos() - event.timestamp) / 1000000
                        + " type=" + event.sensor.getType() + " wake=" + event.sensor.isWakeUpSensor()
                        + " name=" + event.sensor.getName() + " timestamp=" + event.timestamp
                        + " values=" + Arrays.toString(event.values));
            }
        };
        for (Sensor sensor : manager.getSensorList(Sensor.TYPE_ALL)) {
            int type = sensor.getType();
            if (type == 5 || type == 33171001 || type == 33171007 || type == 33171055
                    || type == 33171085 || type == 33171088 || type == 33171089) {
                boolean registered = manager.registerListener(listener, sensor, 200000, handler);
                System.out.println("REGISTER " + registered + " " + sensor.getName() + " type=" + type);
            }
        }
        handler.postDelayed(() -> {
            manager.unregisterListener(listener);
            System.out.println("COMPLETE counts=" + counts);
            ranges.forEach((key, range) -> System.out.println("RANGE " + key + "=" + Arrays.toString(range)));
            System.exit(0);
        }, durationMs);
        Looper.loop();
    }
}
