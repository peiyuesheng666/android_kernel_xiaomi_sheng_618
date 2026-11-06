// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.dolby;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.Switch;
import android.widget.TextView;

public final class AtmosActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView status;
    private AtmosApplication controller;
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            status.setText(!controller.isRequested() ? R.string.disabled
                    : controller.isActive() ? R.string.enabled : R.string.waiting);
            handler.postDelayed(this, 1000);
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        controller = (AtmosApplication) getApplication();
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER_VERTICAL);
        int padding = (int) (32 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, padding, padding, padding);
        TextView title = new TextView(this);
        title.setText(R.string.app_name);
        title.setTextSize(28);
        layout.addView(title);
        Switch toggle = new Switch(this);
        toggle.setText(R.string.switch_label);
        toggle.setChecked(controller.isRequested());
        toggle.setOnCheckedChangeListener((button, enabled) -> controller.setRequested(enabled));
        layout.addView(toggle);
        status = new TextView(this);
        layout.addView(status);
        setContentView(layout);
    }

    @Override public void onResume() { super.onResume(); handler.post(refresh); }
    @Override public void onPause() { handler.removeCallbacks(refresh); super.onPause(); }
}
