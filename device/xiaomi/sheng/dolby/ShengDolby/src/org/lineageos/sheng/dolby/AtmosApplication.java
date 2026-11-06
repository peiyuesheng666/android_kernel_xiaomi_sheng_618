// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.dolby;

import android.app.Application;
import android.content.SharedPreferences;
import android.media.audiofx.AudioEffect;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.ServiceManager;
import android.util.Log;
import java.util.UUID;

/** Owns the actual stock DAP effect handle, including while its UI is closed. */
public final class AtmosApplication extends Application {
    private static final UUID DAP = UUID.fromString("9d4921da-8225-4f29-aefa-39537a04bcaa");
    private static final UUID TYPE_NULL = UUID.fromString("ec7178ec-e5e1-4432-a3f4-4657e6795210");
    private SharedPreferences preferences;
    private Handler worker;
    private AudioEffect effect;
    private Boolean appliedDsState;
    private volatile boolean requested;
    private volatile boolean active;
    private final Runnable reconcile = this::applyEffect;
    private IBinder audioServer;
    private final IBinder.DeathRecipient serverDeath = () -> worker.post(() -> {
        // The server is already gone, so releasing its stale handle cannot
        // enter the vendor DAP destructor on a live audio thread.
        audioServer = null;
        releaseEffect();
        worker.removeCallbacks(reconcile);
        worker.postDelayed(reconcile, 1000);
    });

    @Override public void onCreate() {
        super.onCreate();
        preferences = createDeviceProtectedStorageContext().getSharedPreferences("atmos", MODE_PRIVATE);
        requested = preferences.getBoolean("enabled", true);
        HandlerThread thread = new HandlerThread("ShengAtmos");
        thread.start();
        worker = new Handler(thread.getLooper());
        worker.post(reconcile);
    }

    public boolean isRequested() { return requested; }
    public boolean isActive() { return active; }

    public void setRequested(boolean enabled) {
        requested = enabled;
        preferences.edit().putBoolean("enabled", enabled).apply();
        worker.removeCallbacks(reconcile);
        worker.post(reconcile);
    }

    private void releaseEffect() {
        if (effect != null) {
            try {
                effect.setControlStatusListener(null);
                effect.setEnableStatusListener(null);
                effect.release();
            } catch (RuntimeException error) {
                Log.w("ShengDolby", "Releasing a stale audio handle", error);
            } finally {
                effect = null;
                appliedDsState = null;
            }
        }
        active = false;
    }

    private void applyEffect() {
        worker.removeCallbacks(reconcile);
        try {
            IBinder current = ServiceManager.checkService("media.audio_flinger");
            if (current == null || !current.isBinderAlive()) {
                active = false;
                return;
            }
            if (audioServer == null) {
                current.linkToDeath(serverDeath, 0);
                audioServer = current;
            }
            if (effect == null) {
                boolean available = false;
                AudioEffect.Descriptor[] descriptors = AudioEffect.queryEffects();
                if (descriptors != null) {
                    for (AudioEffect.Descriptor item : descriptors) {
                        if (DAP.equals(item.uuid)) available = true;
                    }
                }
                if (!available) throw new IllegalStateException("Stock DAP is not registered yet");
                effect = new AudioEffect(TYPE_NULL, DAP, 10, 0);
                effect.setControlStatusListener((unused, hasControl) -> {
                    if (!hasControl) active = false;
                    worker.removeCallbacks(reconcile);
                    worker.post(reconcile);
                });
                effect.setEnableStatusListener((unused, enabled) -> {
                    active = requested && enabled;
                });
            }
            boolean control = effect.hasControl();
            boolean enabled = effect.getEnabled();
            if (control && (appliedDsState == null || appliedDsState != requested)) {
                StockDms.setEnabled(effect, requested);
                appliedDsState = requested;
            }
            // Retain the live handle when disabled or temporarily lacking
            // control. Closing it can block the stock driver during migration
            // between mixer and offload outputs. Reconciliation is read-only
            // unless the requested state actually differs.
            if (control && enabled != requested) {
                int result = effect.setEnabled(requested);
                if (result != AudioEffect.SUCCESS) {
                    active = false;
                    Log.w("ShengDolby", "DAP switch returned " + result);
                    return;
                }
                enabled = effect.getEnabled();
            }
            active = requested && Boolean.TRUE.equals(appliedDsState) && control && enabled;
        } catch (android.os.RemoteException | RuntimeException error) {
            Log.w("ShengDolby", "DAP unavailable; waiting for the audio stack", error);
            active = false;
        } finally {
            worker.removeCallbacks(reconcile);
            worker.postDelayed(reconcile, 30000);
        }
    }
}
