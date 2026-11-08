// SPDX-License-Identifier: Apache-2.0
package org.peiyuesheng.sheng.adbboot;

import android.Manifest;
import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.Log;

public final class EnableJob extends JobService {
    static final String TAG = "ShengAdbBoot";
    static final int JOB = 61801;
    static final String WIFI_KEY = "adb_wifi_enabled";
    private final Handler handler = new Handler(Looper.getMainLooper());

    static SharedPreferences prefs(Context context) {
        return context.createDeviceProtectedStorageContext().getSharedPreferences("boot", MODE_PRIVATE);
    }

    static int boot(Context context) {
        return Settings.Global.getInt(context.getContentResolver(), "boot_count", -1);
    }

    static void schedule(Context context) {
        SharedPreferences state = prefs(context);
        if (!state.getBoolean("enabled", false) || boot(context) < 0
                || state.getInt("completed_boot", -2) == boot(context)) return;
        JobInfo info = new JobInfo.Builder(JOB, new ComponentName(context, EnableJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setMinimumLatency(1000).setOverrideDeadline(30000)
                .setBackoffCriteria(30000, JobInfo.BACKOFF_POLICY_LINEAR)
                .setPersisted(true).build();
        int result = context.getSystemService(JobScheduler.class).schedule(info);
        Log.i(TAG, "schedule boot=" + boot(context) + " result=" + result);
    }

    private boolean wifiReady() {
        ConnectivityManager cm = getSystemService(ConnectivityManager.class);
        for (Network network : cm.getAllNetworks()) {
            NetworkCapabilities cap = cm.getNetworkCapabilities(network);
            if (cap != null && cap.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) return true;
        }
        return false;
    }

    @Override public boolean onStartJob(JobParameters params) {
        SharedPreferences state = prefs(this);
        final int currentBoot = boot(this);
        if (!state.getBoolean("enabled", false) || currentBoot < 0
                || state.getInt("completed_boot", -2) == currentBoot) return false;
        if (checkSelfPermission(Manifest.permission.WRITE_SECURE_SETTINGS)
                != PackageManager.PERMISSION_GRANTED) {
            Log.e(TAG, "WRITE_SECURE_SETTINGS not granted; stopped without changing settings");
            return false;
        }
        int attempts = state.getInt("attempt_boot", -1) == currentBoot
                ? state.getInt("attempts", 0) : 0;
        if (attempts >= 8) {
            Log.w(TAG, "bounded startup retries exhausted");
            return false;
        }
        state.edit().putInt("attempt_boot", currentBoot).putInt("attempts", attempts + 1).commit();
        if (!wifiReady()) {
            Log.i(TAG, "Wi-Fi not ready; defer startup attempt=" + (attempts + 1));
            handler.post(() -> jobFinished(params, true));
            return true;
        }
        try {
            // Framework verifies trusted Wi-Fi and paired keys. No TCP 5555 or auth changes.
            if (!Settings.Global.putInt(getContentResolver(), WIFI_KEY, 1)) {
                handler.post(() -> jobFinished(params, true));
                return true;
            }
            handler.postDelayed(() -> {
                boolean enabled = Settings.Global.getInt(getContentResolver(), WIFI_KEY, 0) == 1;
                if (enabled) state.edit().putInt("completed_boot", currentBoot).commit();
                Log.i(TAG, "framework wireless setting=" + enabled + " boot=" + currentBoot);
                jobFinished(params, !enabled);
            }, 3000);
            return true;
        } catch (SecurityException error) {
            Log.e(TAG, "framework refused wireless startup", error);
            return false;
        }
    }

    @Override public boolean onStopJob(JobParameters params) {
        handler.removeCallbacksAndMessages(null);
        return prefs(this).getBoolean("enabled", false);
    }
}
