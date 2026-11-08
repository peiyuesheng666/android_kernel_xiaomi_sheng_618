// SPDX-License-Identifier: Apache-2.0
package org.peiyuesheng.sheng.adbboot;

import android.Manifest;
import android.app.Activity;
import android.app.job.JobScheduler;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private TextView status;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        if (!EnableJob.prefs(this).getBoolean("initialized", false)) {
            EnableJob.prefs(this).edit().putBoolean("initialized", true)
                    .putBoolean("enabled", true).commit();
            EnableJob.schedule(this);
        }
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (24 * getResources().getDisplayMetrics().density);
        layout.setPadding(pad, pad, pad, pad);
        TextView title = new TextView(this);
        title.setText("无线调试开机恢复"); title.setTextSize(24);
        layout.addView(title);
        status = new TextView(this); status.setTextSize(16); layout.addView(status);
        Button enable = new Button(this); enable.setText("启用开机恢复");
        enable.setOnClickListener(v -> {
            EnableJob.prefs(this).edit().putBoolean("enabled", true)
                    .remove("completed_boot").remove("attempt_boot").remove("attempts").commit();
            EnableJob.schedule(this); refresh();
        });
        layout.addView(enable);
        Button disable = new Button(this); disable.setText("关闭开机恢复");
        disable.setOnClickListener(v -> {
            EnableJob.prefs(this).edit().putBoolean("enabled", false).commit();
            getSystemService(JobScheduler.class).cancel(EnableJob.JOB); refresh();
        });
        layout.addView(disable); setContentView(layout); refresh();
    }

    private void refresh() {
        boolean granted = checkSelfPermission(Manifest.permission.WRITE_SECURE_SETTINGS)
                == PackageManager.PERMISSION_GRANTED;
        status.setText("开机恢复：" + (EnableJob.prefs(this).getBoolean("enabled", false) ? "已启用" : "已关闭")
                + "\n系统设置授权：" + (granted ? "已授权" : "待电脑授权")
                + "\n连接已信任的 Wi-Fi 后恢复系统无线调试，沿用原有配对。"
                + "\n每次开机恢复一次，之后手动关闭无线调试不会被反复打开。");
    }
}
