// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.dolby;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.widget.TextView;

/** API 1 Settings/audio-panel entry; unsupported features stay inactive. */
public final class CompatibilityActivity extends Activity {
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        CompatibilityApplication app = (CompatibilityApplication) getApplication();
        if (CompatibilityApplication.platformApi() >= 35 && app.controller() != null) {
            Intent page = new Intent();
            page.setClassName(this, "org.lineageos.sheng.dolby.AtmosActivity");
            startActivity(page); finish(); return;
        }
        setTitle(R.string.app_name);
        TextView explanation = new TextView(this);
        explanation.setText(R.string.unsupported_platform);
        explanation.setTextSize(18);
        explanation.setPadding(24, 24, 24, 24);
        setContentView(explanation);
    }
}
