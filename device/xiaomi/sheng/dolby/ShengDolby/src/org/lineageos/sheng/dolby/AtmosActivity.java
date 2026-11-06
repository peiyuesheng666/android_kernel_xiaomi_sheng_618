// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.dolby;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.res.Configuration;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toolbar;
import java.util.Locale;

public final class AtmosActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final int[] modes = {0, 1, 2, 8, 3};
    private final int[] modeLabels = {R.string.dynamic, R.string.movie, R.string.music, R.string.voice, R.string.custom};
    private final int[] modeDescriptions = {R.string.dynamic_description, R.string.movie_description,
            R.string.music_description, R.string.voice_description, R.string.custom_description};
    private AtmosApplication controller;
    private Switch toggle, dialog;
    private TextView status, modeDescription, toneValue, eqHint, amountValue;
    private RadioGroup profiles;
    private final RadioButton[] modeButtons = new RadioButton[5];
    private final SeekBar[] bands = new SeekBar[5];
    private final TextView[] bandValues = new TextView[5];
    private SeekBar amount;
    private Button reset;
    private LinearLayout toneRow;
    private boolean updating, dragging, dark;
    private int accent, surface, secondary, primary;
    private long seen = -1;
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            if (!dragging && seen != controller.getState().version) update();
            handler.postDelayed(this, 400);
        }
    };
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private int color(int attr) {
        TypedValue value = new TypedValue(); getTheme().resolveAttribute(attr, value, true);
        return value.resourceId == 0 ? value.data : getColor(value.resourceId);
    }
    private LinearLayout column() {
        LinearLayout layout = new LinearLayout(this); layout.setOrientation(LinearLayout.VERTICAL); return layout;
    }
    private GradientDrawable shape(int fill) {
        GradientDrawable drawable = new GradientDrawable(); drawable.setColor(fill); drawable.setCornerRadius(dp(24)); return drawable;
    }
    private TextView text(int resource, int size, boolean bold) {
        TextView view = new TextView(this); view.setText(resource); view.setTextSize(size);
        view.setTextColor(bold ? primary : secondary);
        if (bold) view.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        return view;
    }
    private LinearLayout card(LinearLayout parent) {
        LinearLayout card = column(); card.setPadding(dp(24), dp(22), dp(24), dp(22));
        card.setBackground(shape(surface));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2); params.bottomMargin = dp(16);
        parent.addView(card, params); return card;
    }
    private void heading(LinearLayout parent, int label) {
        TextView title = text(label, 20, true);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2); params.bottomMargin = dp(12);
        parent.addView(title, params);
    }
    @Override public void onCreate(Bundle saved) {
        setTheme(R.style.ShengDolbyTheme);
        super.onCreate(saved);
        controller = (AtmosApplication) getApplication();
        dark = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        accent = color(android.R.attr.colorAccent);
        primary = color(android.R.attr.textColorPrimary);
        secondary = color(android.R.attr.textColorSecondary);
        surface = dark ? 0xff202127 : 0xffffffff;
        LinearLayout root = column(); root.setBackgroundColor(dark ? 0xff121318 : 0xfff3f4f8);
        getWindow().setDecorFitsSystemWindows(false);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom); return insets;
        });
        Toolbar toolbar = new Toolbar(this); toolbar.setTitle(R.string.app_name);
        toolbar.setTitleTextColor(primary); toolbar.setNavigationIcon(R.drawable.ic_arrow_back);
        toolbar.setNavigationContentDescription(R.string.back);
        toolbar.setNavigationOnClickListener(view -> finish());
        root.addView(toolbar, new LinearLayout.LayoutParams(-1, dp(64)));
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        LinearLayout outer = column(); outer.setGravity(Gravity.TOP | Gravity.CENTER_HORIZONTAL);
        outer.setPadding(dp(24), dp(8), dp(24), dp(24)); scroll.addView(outer);
        int width = getResources().getConfiguration().screenWidthDp;
        LinearLayout content = column();
        outer.addView(content, new LinearLayout.LayoutParams(width > 936 ? dp(888) : -1, -2));
        LinearLayout power = card(content);
        power.setBackground(shape(getColor(dark ? android.R.color.system_accent1_800 : android.R.color.system_accent1_100)));
        toggle = new Switch(this); toggle.setText(R.string.switch_label); toggle.setTextSize(20); toggle.setTextColor(primary);
        toggle.setMinHeight(dp(48)); power.addView(toggle, new LinearLayout.LayoutParams(-1, -2));
        status = text(R.string.waiting, 14, false); power.addView(status);
        toggle.setOnCheckedChangeListener((button, enabled) -> { if (!updating) controller.setRequested(enabled); });
        LinearLayout columns = new LinearLayout(this);
        boolean wide = width >= 840;
        columns.setOrientation(wide ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL); content.addView(columns);
        LinearLayout left = column(), right = column();
        LinearLayout.LayoutParams leftParams = new LinearLayout.LayoutParams(wide ? 0 : -1, -2, wide ? 0.9f : 0);
        leftParams.rightMargin = wide ? dp(16) : 0;
        columns.addView(left, leftParams);
        columns.addView(right, new LinearLayout.LayoutParams(wide ? 0 : -1, -2, wide ? 1.1f : 0));
        LinearLayout modeCard = card(left); heading(modeCard, R.string.sound_mode);
        profiles = new RadioGroup(this); modeCard.addView(profiles);
        for (int i = 0; i < modes.length; i++) {
            RadioButton button = new RadioButton(this); button.setId(View.generateViewId());
            button.setText(modeLabels[i]); button.setTextSize(17); button.setMinHeight(dp(48));
            modeButtons[i] = button; profiles.addView(button, new RadioGroup.LayoutParams(-1, dp(48)));
            final int mode = modes[i];
            button.setOnCheckedChangeListener((unused, checked) -> { if (checked && !updating) controller.setProfile(mode); });
        }
        modeDescription = text(R.string.dynamic_description, 14, false); modeDescription.setPadding(0, dp(8), 0, 0);
        modeCard.addView(modeDescription);
        LinearLayout tuning = card(left); heading(tuning, R.string.sound_tuning);
        toneRow = new LinearLayout(this); toneRow.setGravity(Gravity.CENTER_VERTICAL); toneRow.setMinimumHeight(dp(56));
        toneRow.addView(text(R.string.tone, 17, true), new LinearLayout.LayoutParams(0, -2, 1));
        toneValue = text(R.string.detailed, 16, false); toneValue.setTextColor(accent); toneRow.addView(toneValue);
        toneRow.setContentDescription(getString(R.string.tone)); toneRow.setClickable(true); toneRow.setFocusable(true);
        TypedValue selectable = new TypedValue(); getTheme().resolveAttribute(android.R.attr.selectableItemBackground, selectable, true);
        toneRow.setForeground(getDrawable(selectable.resourceId)); tuning.addView(toneRow);
        toneRow.setOnClickListener(view -> {
            String[] labels = getResources().getStringArray(R.array.tone_labels);
            new AlertDialog.Builder(this).setTitle(R.string.tone)
                    .setSingleChoiceItems(labels, Math.max(0, Math.min(3, controller.getState().ieq)), (popup, which) -> {
                        controller.setParameter(StockDms.IEQ, which); popup.dismiss();
                    }).setNegativeButton(android.R.string.cancel, null).show();
        });
        dialog = new Switch(this); dialog.setText(R.string.dialog_enhancement); dialog.setTextSize(17);
        dialog.setMinHeight(dp(56)); tuning.addView(dialog, new LinearLayout.LayoutParams(-1, -2));
        dialog.setOnCheckedChangeListener((button, enabled) -> { if (!updating) controller.setParameter(StockDms.DIALOG, enabled ? 1 : 0); });
        amountValue = text(R.string.strength, 14, false); tuning.addView(amountValue);
        amount = new SeekBar(this); amount.setMax(16); amount.setContentDescription(getString(R.string.dialog_strength));
        tuning.addView(amount, new LinearLayout.LayoutParams(-1, dp(48)));
        amount.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar bar, int progress, boolean user) {
                amountValue.setText(getString(R.string.strength_percent, Math.round(progress * 100f / 16)));
            }
            public void onStartTrackingTouch(SeekBar bar) { dragging = true; }
            public void onStopTrackingTouch(SeekBar bar) { dragging = false; controller.setParameter(StockDms.DIALOG_AMOUNT, bar.getProgress()); }
        });
        LinearLayout eq = card(right); heading(eq, R.string.equalizer);
        eqHint = text(R.string.eq_hint, 14, false); eq.addView(eqHint);
        int[] names = {R.string.bass, R.string.low_mid, R.string.mid, R.string.high_mid, R.string.treble};
        for (int i = 0; i < 5; i++) {
            LinearLayout row = new LinearLayout(this); row.setGravity(Gravity.CENTER_VERTICAL); row.setPadding(0, dp(12), 0, 0);
            row.addView(text(names[i], 16, true), new LinearLayout.LayoutParams(0, -2, 1));
            bandValues[i] = text(R.string.zero_db, 14, false); row.addView(bandValues[i]); eq.addView(row);
            bands[i] = new SeekBar(this); bands[i].setMax(12); bands[i].setProgress(6);
            bands[i].setContentDescription(getString(names[i])); eq.addView(bands[i], new LinearLayout.LayoutParams(-1, dp(48)));
            final int band = i;
            bands[i].setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
                public void onProgressChanged(SeekBar bar, int progress, boolean user) {
                    bandValues[band].setText(String.format(Locale.getDefault(), "%+d dB", progress - 6));
                }
                public void onStartTrackingTouch(SeekBar bar) { dragging = true; }
                public void onStopTrackingTouch(SeekBar bar) {
                    int[] values = controller.getState().gains.clone();
                    for (int n = band * 4; n < band * 4 + 4; n++) values[n] = (bar.getProgress() - 6) * 64;
                    dragging = false; controller.setParameter(StockDms.GAINS, values);
                }
            });
        }
        reset = new Button(this); reset.setText(R.string.reset_profile); reset.setAllCaps(false);
        eq.addView(reset, new LinearLayout.LayoutParams(-1, dp(52)));
        reset.setOnClickListener(view -> new AlertDialog.Builder(this).setTitle(R.string.reset_profile)
                .setMessage(R.string.reset_description).setNegativeButton(android.R.string.cancel, null)
                .setPositiveButton(R.string.reset, (popup, which) -> controller.resetProfile()).show());
        setContentView(root); update();
    }
    private void update() {
        AtmosApplication.State state = controller.getState(); seen = state.version; updating = true;
        toggle.setChecked(state.requested);
        status.setText(state.failed ? R.string.apply_failed : !state.requested ? R.string.disabled
                : state.active ? R.string.enabled : R.string.waiting);
        boolean controls = state.ready && state.requested;
        for (int i = 0; i < modes.length; i++) {
            modeButtons[i].setEnabled(controls); modeButtons[i].setChecked(state.profile == modes[i]);
            if (state.profile == modes[i]) modeDescription.setText(modeDescriptions[i]);
        }
        String[] labels = getResources().getStringArray(R.array.tone_labels);
        toneValue.setText(labels[Math.max(0, Math.min(3, state.ieq))]); toneRow.setEnabled(controls);
        dialog.setChecked(state.dialog); dialog.setEnabled(controls);
        amount.setProgress(state.dialogAmount); amount.setEnabled(controls && state.dialog);
        boolean custom = state.profile == 3;
        eqHint.setText(custom ? R.string.eq_description : R.string.eq_hint);
        for (int i = 0; i < bands.length; i++) {
            int total = 0; for (int n = i * 4; n < i * 4 + 4; n++) total += state.gains[n];
            bands[i].setProgress(Math.max(0, Math.min(12, Math.round(total / 256f) + 6)));
            bands[i].setEnabled(controls && custom);
        }
        reset.setEnabled(controls); updating = false;
    }
    @Override public void onResume() { super.onResume(); handler.post(refresh); }
    @Override public void onPause() { handler.removeCallbacks(refresh); super.onPause(); }
}
