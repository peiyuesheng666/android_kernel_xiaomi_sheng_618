// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.dolby;

import android.app.Application;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.media.audiofx.AudioEffect;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.ServiceManager;
import android.util.Log;
import java.util.Arrays;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/** Serializes controls and retains the native effect while its page is closed. */
public final class AtmosApplication extends Application {
    private static final UUID DAP = UUID.fromString("9d4921da-8225-4f29-aefa-39537a04bcaa");
    private static final UUID TYPE_NULL = UUID.fromString("ec7178ec-e5e1-4432-a3f4-4657e6795210");
    private static final int[] PARAMETERS = {104, 105, 106, 108, 110};
    public static final class State {
        public final long version;
        public final boolean requested, active, ready, failed, dialog;
        public final int profile, ieq, dialogAmount;
        public final int[] gains;
        State(long v, boolean wanted, boolean on, boolean valid, boolean error,
                int mode, int tone, boolean voice, int amount, int[] bands) {
            version = v; requested = wanted; active = on; ready = valid; failed = error;
            profile = mode; ieq = tone; dialog = voice; dialogAmount = amount; gains = bands.clone();
        }
    }
    private volatile State state = new State(0, true, false, false, false, 0, 1, false, 6, new int[20]);
    private volatile boolean requested;
    private int desiredProfile;
    private boolean restored;
    private SharedPreferences preferences;
    private Handler worker;
    private AudioEffect effect;
    private IBinder audioServer;
    private long version;
    private final ConcurrentHashMap<String, AtomicLong> parameterVersions = new ConcurrentHashMap<>();
    private final Runnable reconcile = this::applyEffect;
    private final IBinder.DeathRecipient serverDeath = () -> worker.post(() -> {
        audioServer = null;
        if (effect != null) {
            try { effect.release(); } catch (RuntimeException ignored) { }
            effect = null;
        }
        restored = false;
        worker.removeCallbacks(reconcile);
        worker.postDelayed(reconcile, 1000);
    });
    @Override public void onCreate() {
        super.onCreate();
        preferences = createDeviceProtectedStorageContext().getSharedPreferences("atmos", MODE_PRIVATE);
        requested = preferences.getBoolean("enabled", true);
        desiredProfile = preferences.getInt("profile", -1);
        HandlerThread thread = new HandlerThread("ShengAtmos"); thread.start();
        worker = new Handler(thread.getLooper()); worker.post(reconcile);
    }
    public State getState() { return state; }
    @Override public void onConfigurationChanged(Configuration configuration) {
        super.onConfigurationChanged(configuration);
        worker.removeCallbacks(reconcile); worker.post(reconcile);
    }
    public void setRequested(boolean enabled) {
        requested = enabled;
        preferences.edit().putBoolean("enabled", enabled).apply();
        worker.removeCallbacks(reconcile); worker.post(reconcile);
    }
    public void setProfile(int profile) {
        if (profile != 0 && profile != 1 && profile != 2 && profile != 3 && profile != 8) return;
        worker.post(() -> {
            desiredProfile = profile;
            preferences.edit().putInt("profile", profile).apply();
            restored = false; applyEffect();
        });
    }
    public void setParameter(int parameter, int... values) {
        final int profile = state.profile;
        final int[] data = values.clone();
        final AtomicLong generation = parameterVersions.computeIfAbsent(key(profile, parameter),
                unused -> new AtomicLong());
        final long sequence = generation.incrementAndGet();
        worker.post(() -> {
            if (generation.get() != sequence) return;
            try {
                if (effect == null || !effect.hasControl()) throw new IllegalStateException("No DAP control");
                StockDms.setParameter(effect, profile, parameter, data);
                if (parameter == StockDms.GAINS) {
                    StockDms.setParameter(effect, profile, StockDms.GEQ, 1);
                }
                worker.postDelayed(() -> {
                    if (generation.get() != sequence) return;
                    try {
                        if (!Arrays.equals(data, StockDms.getParameter(effect, profile, parameter)))
                            throw new IllegalStateException("Parameter readback mismatch: " + parameter);
                        remember(profile, parameter, data);
                        if (parameter == StockDms.GAINS) remember(profile, StockDms.GEQ, new int[]{1});
                        readState(false);
                        Log.i("ShengDolby", "Verified profile=" + profile + " parameter=" + parameter
                                + " values=" + Arrays.toString(data));
                    } catch (RuntimeException error) { reportError(error); }
                }, 150);
            } catch (RuntimeException error) { reportError(error); }
        });
    }
    public void resetProfile() {
        final int profile = state.profile;
        worker.post(() -> {
            try {
                StockDms.resetProfile(effect, profile);
                StockDms.setParameter(effect, profile, StockDms.GAINS, new int[20]);
                SharedPreferences.Editor edit = preferences.edit();
                for (int parameter : PARAMETERS) edit.remove(key(profile, parameter));
                edit.apply();
                worker.postDelayed(() -> {
                    try { readState(false); } catch (RuntimeException error) { reportError(error); }
                }, 150);
            } catch (RuntimeException error) { reportError(error); }
        });
    }
    private String key(int profile, int parameter) { return "param." + profile + "." + parameter; }
    private void remember(int profile, int parameter, int[] data) {
        StringBuilder value = new StringBuilder();
        for (int item : data) { if (value.length() != 0) value.append(','); value.append(item); }
        preferences.edit().putString(key(profile, parameter), value.toString()).apply();
    }
    private void restoreParameters(int profile) {
        for (int parameter : PARAMETERS) {
            String saved = preferences.getString(key(profile, parameter), null);
            if (saved == null) {
                // Start unsaved EQ profiles flat without replacing user presets.
                if (parameter == StockDms.GAINS)
                    StockDms.setParameter(effect, profile, parameter, new int[20]);
                continue;
            }
            String[] parts = saved.split(",");
            int[] values = new int[parts.length];
            for (int i = 0; i < values.length; i++) values[i] = Integer.parseInt(parts[i]);
            StockDms.setParameter(effect, profile, parameter, values);
        }
    }
    private void readState(boolean failed) {
        int profile = StockDms.getProfile(effect);
        boolean enabled = StockDms.isEnabled(effect);
        state = new State(++version, requested, requested && enabled && effect.getEnabled(), true,
                failed, profile, StockDms.getParameter(effect, profile, StockDms.IEQ)[0],
                StockDms.getParameter(effect, profile, StockDms.DIALOG)[0] != 0,
                StockDms.getParameter(effect, profile, StockDms.DIALOG_AMOUNT)[0],
                StockDms.getParameter(effect, profile, StockDms.GAINS));
    }
    private void reportError(Exception error) {
        Log.w("ShengDolby", "Unable to apply Dolby setting", error);
        State old = state;
        state = new State(++version, requested, false, old.ready, true,
                old.profile, old.ieq, old.dialog, old.dialogAmount, old.gains);
    }
    private void applyEffect() {
        worker.removeCallbacks(reconcile);
        try {
            IBinder current = ServiceManager.checkService("media.audio_flinger");
            if (current == null || !current.isBinderAlive()) throw new IllegalStateException("Audio server unavailable");
            if (audioServer == null) { current.linkToDeath(serverDeath, 0); audioServer = current; }
            SpeakerTuning.apply(getResources().getConfiguration().orientation == Configuration.ORIENTATION_LANDSCAPE);
            if (effect == null) {
                effect = new AudioEffect(TYPE_NULL, DAP, 10, 0);
                effect.setControlStatusListener((unused, control) -> {
                    worker.removeCallbacks(reconcile); worker.post(reconcile);
                });
            }
            if (!effect.hasControl()) throw new IllegalStateException("DAP temporarily lacks control");
            if (StockDms.isEnabled(effect) != requested) StockDms.setEnabled(effect, requested);
            if (effect.getEnabled() != requested) {
                int result = effect.setEnabled(requested);
                if (result != AudioEffect.SUCCESS) throw new IllegalStateException("DAP switch: " + result);
            }
            if (!restored) {
                if (desiredProfile < 0) desiredProfile = StockDms.getProfile(effect);
                if (StockDms.getProfile(effect) != desiredProfile) StockDms.setProfile(effect, desiredProfile);
                restoreParameters(desiredProfile); restored = true;
            }
            worker.postDelayed(() -> {
                try {
                    readState(false);
                    if (state.profile != desiredProfile || StockDms.isEnabled(effect) != requested)
                        throw new IllegalStateException("Mode/switch readback mismatch");
                } catch (RuntimeException error) { restored = false; reportError(error); }
            }, 150);
        } catch (android.os.RemoteException | RuntimeException error) { reportError(error); }
        finally { worker.removeCallbacks(reconcile); worker.postDelayed(reconcile, 30000); }
    }
}
