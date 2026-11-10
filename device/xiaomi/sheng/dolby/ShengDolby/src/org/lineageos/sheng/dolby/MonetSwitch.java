// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.dolby;

import android.animation.ValueAnimator;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.view.Gravity;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.CompoundButton;

/** Modern capsule switch, retaining CompoundButton interaction and accessibility. */
final class MonetSwitch extends CompoundButton {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF track = new RectF();
    private final int active, onActive, inactive, outline;
    private final boolean prominent;
    private float position;
    private ValueAnimator motion;

    MonetSwitch(Context context, boolean prominent, int active, int onActive,
            int inactive, int outline, ColorStateList textColors) {
        super(context);
        this.prominent = prominent;
        this.active = active; this.onActive = onActive;
        this.inactive = inactive; this.outline = outline;
        setButtonDrawable(null);
        setGravity(Gravity.CENTER_VERTICAL);
        setMinHeight(dp(prominent ? 72 : 56));
        setPaddingRelative(0, dp(8), dp(prominent ? 84 : 72), dp(8));
        setTextSize(prominent ? 22 : 17);
        setTextColor(textColors);
        setFocusable(true);
        GradientDrawable mask = new GradientDrawable();
        mask.setColor(0xffffffff); mask.setCornerRadius(dp(24));
        setBackground(new RippleDrawable(ColorStateList.valueOf((active & 0xffffff) | 0x18000000), null, mask));
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    @Override public void setChecked(boolean checked) {
        boolean changed = checked != isChecked();
        super.setChecked(checked);
        if (!changed) return;
        if (motion != null) motion.cancel();
        float target = checked ? 1f : 0f;
        if (!isLaidOut() || !isShown()) { position = target; invalidate(); return; }
        motion = ValueAnimator.ofFloat(position, target);
        motion.setDuration(180);
        motion.addUpdateListener(value -> { position = (float) value.getAnimatedValue(); invalidate(); });
        motion.start();
    }

    @Override protected void onDetachedFromWindow() {
        if (motion != null) motion.cancel();
        position = isChecked() ? 1f : 0f;
        super.onDetachedFromWindow();
    }

    private int mix(int a, int b, float fraction) {
        int r = Math.round(((a >> 16) & 255) * (1-fraction) + ((b >> 16) & 255) * fraction);
        int g = Math.round(((a >> 8) & 255) * (1-fraction) + ((b >> 8) & 255) * fraction);
        int blue = Math.round((a & 255) * (1-fraction) + (b & 255) * fraction);
        return 0xff000000 | (r << 16) | (g << 8) | blue;
    }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float width = dp(prominent ? 64 : 52), height = dp(prominent ? 36 : 32);
        boolean rtl = getLayoutDirection() == LAYOUT_DIRECTION_RTL;
        float left = rtl ? dp(4) : getWidth() - dp(4) - width;
        float top = (getHeight() - height) / 2f;
        track.set(left, top, left + width, top + height);
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(mix(inactive, active, position));
        paint.setAlpha(isEnabled() ? 255 : 97);
        canvas.drawRoundRect(track, height/2, height/2, paint);
        if (position < 1f) {
            paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(dp(2));
            paint.setColor(outline); paint.setAlpha(Math.round((isEnabled() ? 255 : 97) * (1-position)));
            RectF border = new RectF(track); border.inset(dp(1), dp(1));
            canvas.drawRoundRect(border, height/2, height/2, paint);
        }
        float p = rtl ? 1-position : position;
        float center = left + height/2 + (width-height)*p;
        float radius = dp(prominent ? 10 : 8) + dp(4)*position;
        paint.setStyle(Paint.Style.FILL); paint.setColor(mix(outline, onActive, position));
        paint.setAlpha(isEnabled() ? 255 : 97);
        canvas.drawCircle(center, top + height/2, radius, paint);
        if (position > .5f) {
            paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(dp(2));
            paint.setStrokeCap(Paint.Cap.ROUND); paint.setColor(active);
            paint.setAlpha(Math.round((isEnabled() ? 255 : 97)*(position-.5f)*2));
            float y = top + height/2;
            canvas.drawLine(center-dp(4), y, center-dp(1), y+dp(3), paint);
            canvas.drawLine(center-dp(1), y+dp(3), center+dp(5), y-dp(3), paint);
        }
    }

    @Override public void onInitializeAccessibilityNodeInfo(AccessibilityNodeInfo info) {
        super.onInitializeAccessibilityNodeInfo(info);
        info.setClassName("android.widget.Switch");
    }
}
