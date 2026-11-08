// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.facelab;

import android.Manifest;
import android.app.Activity;
import android.app.KeyguardManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.ImageFormat;
import android.graphics.Matrix;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.RectF;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.CaptureResult;
import android.hardware.camera2.TotalCaptureResult;
import android.hardware.camera2.params.Face;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.hardware.display.DisplayManager;
import android.media.Image;
import android.media.ImageReader;
import android.os.Bundle;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.util.Size;
import android.view.Surface;
import android.view.View;
import android.view.WindowManager;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.Arrays;
import java.util.Collections;
import java.util.Locale;
import java.util.TreeMap;
import java.util.concurrent.atomic.AtomicLong;

/** User-operated development UI. Never registers a biometric sensor or unlocks the device. */
public final class FaceLabActivity extends Activity {
    private static final int CAMERA_PERMISSION = 10, CONFIRM_CREDENTIAL = 11;
    private final SampleCollector collector = new SampleCollector();
    private final AtomicLong epoch = new AtomicLong();
    private final TreeMap<Long, FrameInfo> metadata = new TreeMap<>();
    private HandlerThread cameraThread;
    private Handler worker;
    private TextView status;
    private Preview preview;
    private TemplateStore store;
    // Camera resources, descriptors and capture state are confined to worker.
    private CameraDevice camera;
    private CameraCaptureSession session;
    private ImageReader reader;
    private Image pendingImage;
    private float[][] enrolled;
    private boolean comparing;
    private long lastFrame, lastUi, enrollmentDeadline;
    private int orientation;
    private int openedDisplayRotation;
    private volatile boolean resumed, cameraRequested;
    private volatile long credentialDeadline;
    private final DisplayManager.DisplayListener displayListener = new DisplayManager.DisplayListener() {
        @Override public void onDisplayAdded(int id) {}
        @Override public void onDisplayRemoved(int id) {}
        @Override public void onDisplayChanged(int id) {
            if (cameraRequested && getDisplay() != null && id == getDisplay().getDisplayId()
                    && getDisplay().getRotation() != openedDisplayRotation) {
                stopCamera(); message("方向已改变，请重新开启前摄；未完成的采集已取消");
            }
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        store = new TemplateStore(this);
        cameraThread = new HandlerThread("ShengFaceLab-camera"); cameraThread.start();
        worker = new Handler(cameraThread.getLooper());
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        int pad = Math.round(12 * getResources().getDisplayMetrics().density);
        root.setPadding(pad, pad, pad, pad);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            android.graphics.Insets bars = insets.getInsets(
                    WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            view.setPadding(pad + bars.left, pad + bars.top, pad + bars.right, pad + bars.bottom);
            return insets;
        });
        TextView title = new TextView(this); title.setTextSize(22); title.setText("人脸录入测试");
        root.addView(title);
        TextView description = new TextView(this);
        description.setText("自行编写的前摄与特征采集测试。仅点击后开启摄像头。\n"
                + "只在本应用保存加密特征，不保存照片；尚未接入系统解锁。");
        root.addView(description);
        preview = new Preview(); root.addView(preview, new LinearLayout.LayoutParams(-1, 0, 1));
        status = new TextView(this); status.setTextSize(16); root.addView(status);
        button(root, "开启前摄", this::requestCamera);
        button(root, "录入样本（先验证锁屏密码）", this::requestEnrollment);
        button(root, "比较当前人脸", this::requestComparison);
        button(root, "停止前摄", this::stopCamera);
        button(root, "删除已录入样本", () -> {
            collector.cancel(); credentialDeadline = 0;
            worker.post(() -> {
                comparing = false; wipeEnrolled();
                try { store.delete(); message("已删除样本及加密密钥"); }
                catch (Exception e) { message("删除未完成：" + e.getClass().getSimpleName()); }
            });
        });
        setContentView(root); root.requestApplyInsets(); message("前摄尚未开启");
        getSystemService(DisplayManager.class).registerDisplayListener(displayListener, new Handler(getMainLooper()));
    }

    private void button(LinearLayout root, String label, Runnable action) {
        Button button = new Button(this); button.setText(label);
        button.setOnClickListener(v -> action.run()); root.addView(button);
    }
    private void message(String text) { runOnUiThread(() -> status.setText(text)); }
    @Override protected void onResume() { super.onResume(); resumed = true; }
    @Override protected void onPause() {
        resumed = false; stopCamera(); super.onPause();
    }
    @Override protected void onDestroy() {
        getSystemService(DisplayManager.class).unregisterDisplayListener(displayListener);
        stopCamera(); worker.post(this::wipeEnrolled); cameraThread.quitSafely(); super.onDestroy();
    }
    @Override public void onConfigurationChanged(Configuration configuration) {
        super.onConfigurationChanged(configuration);
        stopCamera(); message("方向已改变，请重新开启前摄；未完成的采集已取消");
    }

    private void requestCamera() {
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.CAMERA}, CAMERA_PERMISSION); return;
        }
        if (!resumed || cameraRequested) return;
        cameraRequested = true;
        long token = epoch.incrementAndGet();
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        openedDisplayRotation = getDisplay().getRotation();
        int degrees = openedDisplayRotation * 90;
        message("正在开启普通前摄…");
        worker.post(() -> openCamera(token, degrees));
    }
    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);
        if (code == CAMERA_PERMISSION) {
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED)
                requestCamera();
            else message("未授予前摄权限");
        }
    }
    private boolean current(long token) { return resumed && token == epoch.get(); }
    private void stopCamera() {
        cameraRequested = false; epoch.incrementAndGet(); collector.cancel();
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (preview != null) preview.clear();
        if (worker != null) worker.post(this::closeCamera);
        message("前摄已停止，未完成的采集已取消");
    }
    private void closeCamera() {
        comparing = false; metadata.clear(); lastFrame = 0; lastUi = 0;
        wipeEnrolled();
        if (pendingImage != null) { pendingImage.close(); pendingImage = null; }
        if (session != null) { session.close(); session = null; }
        if (camera != null) { camera.close(); camera = null; }
        if (reader != null) { reader.close(); reader = null; }
    }
    private void cameraFailure(long token, String text) {
        if (!current(token)) return;
        epoch.incrementAndGet(); cameraRequested = false; collector.cancel(); closeCamera();
        runOnUiThread(() -> {
            getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            preview.clear(); status.setText(text);
        });
    }

    private void openCamera(long token, int displayDegrees) {
        if (!current(token)) return;
        try {
            CameraManager manager = getSystemService(CameraManager.class);
            String front = null; CameraCharacteristics characteristics = null;
            for (String id : manager.getCameraIdList()) {
                CameraCharacteristics candidate = manager.getCameraCharacteristics(id);
                Integer facing = candidate.get(CameraCharacteristics.LENS_FACING);
                if (facing != null && facing == CameraCharacteristics.LENS_FACING_FRONT) {
                    front = id; characteristics = candidate; break;
                }
            }
            if (front == null) throw new IllegalStateException("Front camera unavailable");
            int[] modes = characteristics.get(CameraCharacteristics.STATISTICS_INFO_AVAILABLE_FACE_DETECT_MODES);
            int detect = CaptureRequest.STATISTICS_FACE_DETECT_MODE_OFF;
            if (modes != null) for (int mode : modes) detect = Math.max(detect, mode);
            final int faceMode = detect;
            boolean none = false;
            if (Build.VERSION.SDK_INT >= 31) {
                int[] rotations = characteristics.get(CameraCharacteristics.SCALER_AVAILABLE_ROTATE_AND_CROP_MODES);
                if (rotations != null) for (int rotation : rotations)
                    if (rotation == CaptureRequest.SCALER_ROTATE_AND_CROP_NONE) none = true;
            }
            final boolean disableRotateCrop = none;
            Integer sensorDegrees = characteristics.get(CameraCharacteristics.SENSOR_ORIENTATION);
            if (sensorDegrees == null) throw new IllegalStateException("Sensor orientation missing");
            orientation = FrameMath.rotation(sensorDegrees, displayDegrees);
            StreamConfigurationMap map = characteristics.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            Size selected = null;
            if (map != null) for (Size size : map.getOutputSizes(ImageFormat.YUV_420_888)) {
                if (size.getWidth() < 320 || size.getHeight() < 240 || size.getWidth() > 1280
                        || size.getHeight() > 960) continue;
                if (selected == null || sizeCost(size) < sizeCost(selected)) selected = size;
            }
            if (selected == null) throw new IllegalStateException("Ordinary YUV stream unavailable");
            reader = ImageReader.newInstance(selected.getWidth(), selected.getHeight(),
                    ImageFormat.YUV_420_888, 3);
            reader.setOnImageAvailableListener(r -> {
                if (!current(token)) return;
                try {
                    Image next = r.acquireLatestImage();
                    if (next == null) return;
                    if (pendingImage != null) pendingImage.close();
                    pendingImage = next;
                    consumePending(token);
                } catch (Exception e) { cameraFailure(token, "接收前摄帧失败：" + e.getClass().getSimpleName()); }
            }, worker);
            manager.openCamera(front, new CameraDevice.StateCallback() {
                @Override public void onOpened(CameraDevice device) {
                    if (!current(token)) { device.close(); return; }
                    camera = device;
                    try {
                        Surface target = reader.getSurface();
                        device.createCaptureSession(Collections.singletonList(target),
                                new CameraCaptureSession.StateCallback() {
                            @Override public void onConfigured(CameraCaptureSession configured) {
                                if (!current(token)) { configured.close(); return; }
                                session = configured;
                                try {
                                    CaptureRequest.Builder request = device.createCaptureRequest(
                                            CameraDevice.TEMPLATE_PREVIEW);
                                    request.addTarget(target);
                                    request.set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO);
                                    request.set(CaptureRequest.STATISTICS_FACE_DETECT_MODE, faceMode);
                                    if (disableRotateCrop && Build.VERSION.SDK_INT >= 31)
                                        request.set(CaptureRequest.SCALER_ROTATE_AND_CROP,
                                                CaptureRequest.SCALER_ROTATE_AND_CROP_NONE);
                                    configured.setRepeatingRequest(request.build(), new CameraCaptureSession.CaptureCallback() {
                                        @Override public void onCaptureCompleted(CameraCaptureSession s,
                                                CaptureRequest r, TotalCaptureResult result) {
                                            if (!current(token)) return;
                                            Long timestamp = result.get(CaptureResult.SENSOR_TIMESTAMP);
                                            Rect crop = result.get(CaptureResult.SCALER_CROP_REGION);
                                            if (timestamp != null && crop != null) {
                                                metadata.put(timestamp, new FrameInfo(crop,
                                                        result.get(CaptureResult.STATISTICS_FACES)));
                                                while (metadata.size() > 32) metadata.pollFirstEntry();
                                                consumePending(token);
                                            }
                                        }
                                    }, worker);
                                    message(faceMode == 0 ? "前摄可用，但未提供人脸框；暂不能录入"
                                            : "前摄已开启，请保持单人正脸入镜");
                                } catch (Exception e) { cameraFailure(token, "启动预览失败：" + e.getClass().getSimpleName()); }
                            }
                            @Override public void onConfigureFailed(CameraCaptureSession s) {
                                s.close(); cameraFailure(token, "前摄流配置失败");
                            }
                        }, worker);
                    } catch (Exception e) { cameraFailure(token, "配置前摄失败：" + e.getClass().getSimpleName()); }
                }
                @Override public void onDisconnected(CameraDevice device) {
                    device.close(); cameraFailure(token, "前摄已断开");
                }
                @Override public void onError(CameraDevice device, int error) {
                    device.close(); cameraFailure(token, "前摄错误 " + error);
                }
            }, worker);
        } catch (Exception e) { cameraFailure(token, "开启前摄失败：" + e.getClass().getSimpleName()); }
    }
    private static long sizeCost(Size size) {
        return Math.abs((long) size.getWidth() * size.getHeight() - 640 * 480);
    }
    private static FrameMath.Box box(Rect r) { return new FrameMath.Box(r.left, r.top, r.right, r.bottom); }
    private static final class FrameInfo {
        final Rect crop;
        final Face[] faces;
        FrameInfo(Rect crop, Face[] faces) {
            this.crop = new Rect(crop); this.faces = faces == null ? new Face[0] : faces.clone();
        }
    }

    private void requestEnrollment() {
        if (SystemClock.elapsedRealtime() >= credentialDeadline) {
            Intent intent = getSystemService(KeyguardManager.class).createConfirmDeviceCredentialIntent(
                    "确认录入测试", "确认锁屏密码后，重新开启前摄并点击录入样本");
            if (intent == null) { message("请先设置锁屏密码"); return; }
            startActivityForResult(intent, CONFIRM_CREDENTIAL); return;
        }
        worker.post(() -> {
            if (camera == null || !resumed) { message("请先开启前摄，再点击录入样本"); return; }
            if (SystemClock.elapsedRealtime() >= credentialDeadline) {
                message("密码确认已过期，请重新点击录入"); return;
            }
            credentialDeadline = 0; comparing = false; long generation = collector.begin();
            enrollmentDeadline = SystemClock.elapsedRealtime() + 30_000;
            worker.postDelayed(() -> {
                if (collector.generation() == generation && collector.collecting()) {
                    collector.cancel(); message("采集超时，未修改原有样本");
                }
            }, 30_000);
            message("采集 0/12：请保持正脸清晰，允许轻微移动");
        });
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == CONFIRM_CREDENTIAL && result == RESULT_OK) {
            credentialDeadline = SystemClock.elapsedRealtime() + 30_000;
            message("密码已确认，请开启前摄并点击录入样本（30 秒内有效）");
        } else if (request == CONFIRM_CREDENTIAL) {
            credentialDeadline = 0; message("密码确认已取消");
        }
    }
    private void wipeEnrolled() {
        if (enrolled != null) for (float[] item : enrolled) Arrays.fill(item, 0);
        enrolled = null;
    }
    private void requestComparison() {
        worker.post(() -> {
            collector.cancel(); comparing = false; wipeEnrolled();
            try {
                enrolled = store.load(); comparing = enrolled != null && camera != null;
                message(enrolled == null ? "尚未录入样本" : camera == null
                        ? "请先开启前摄" : "正在比较，仅显示特征距离，不执行解锁");
            } catch (Exception e) { message("读取样本失败：" + e.getClass().getSimpleName()); }
        });
    }

    private void consumePending(long token) {
        if (pendingImage == null || !metadata.containsKey(pendingImage.getTimestamp())) return;
        Image image = pendingImage; pendingImage = null;
        processImage(image, token);
    }

    private void processImage(Image acquired, long token) {
        try (Image image = acquired) {
            if (image == null || !current(token)) return;
            long timestamp = image.getTimestamp();
            if (timestamp - lastFrame < 100_000_000L) return;
            lastFrame = timestamp;
            FrameInfo info = metadata.remove(timestamp);
            Image.Plane y = image.getPlanes()[0];
            FrameMath.Plane luma = new FrameMath.Plane(y.getBuffer(), y.getRowStride(),
                    y.getPixelStride(), image.getWidth(), image.getHeight());
            FrameMath.Box face = null;
            String guidance = "等待同帧人脸信息";
            if (info != null) {
                guidance = info.faces.length == 0 ? "未检测到人脸" : "请保持只有一张人脸入镜";
                if (info.faces.length == 1 && info.faces[0].getScore() >= 60) {
                    FrameMath.Box crop = FrameMath.streamCrop(box(info.crop), image.getWidth(), image.getHeight());
                    face = FrameMath.toStream(box(info.faces[0].getBounds()), crop,
                            image.getWidth(), image.getHeight());
                    guidance = face == null ? "请将整张脸移入画面" : "请将脸靠近一些";
                    if (face != null && (face.width() < 96 || face.height() < 96)) face = null;
                }
            }
            render(image, luma, face, token);
            if (collector.collecting() && SystemClock.elapsedRealtime() >= enrollmentDeadline) {
                collector.cancel(); message("采集超时，未修改原有样本"); return;
            }
            if (face == null) { periodic(guidance); return; }
            byte[] normalized = luma.normalized(face, FaceDescriptor.SIZE, orientation);
            float[] descriptor = null;
            try {
                FaceDescriptor.Quality quality = FaceDescriptor.quality(normalized);
                if (!quality.usable()) { periodic("请改善光线并保持画面清晰"); return; }
                descriptor = FaceDescriptor.extract(normalized);
                if (collector.collecting()) {
                    long generation = collector.generation();
                    if (collector.offer(generation, timestamp, descriptor)) {
                        int count = collector.count(); message("采集 " + count + "/12");
                        float[][] complete = collector.completed(generation);
                        if (complete != null) {
                            try {
                                // A pause/configuration change invalidates token before it can persist.
                                if (current(token)) {
                                    store.save(complete); message("已加密保存 12 个特征样本，可点击比较");
                                }
                            } finally { for (float[] sample : complete) Arrays.fill(sample, 0); }
                        }
                    }
                } else if (comparing && enrolled != null) {
                    double sum = 0;
                    for (float[] sample : enrolled) sum += FaceDescriptor.distance(descriptor, sample);
                    periodic(String.format(Locale.ROOT, "平均特征距离 %.4f（越低越相似）\n尚未标定误识率，不用于解锁", sum / enrolled.length));
                } else periodic("正脸质量可用，可开始录入或比较");
            } finally {
                Arrays.fill(normalized, (byte) 0);
                if (descriptor != null) Arrays.fill(descriptor, 0);
            }
        } catch (Exception e) { cameraFailure(token, "处理前摄帧失败：" + e.getClass().getSimpleName()); }
    }
    private void periodic(String text) {
        long now = SystemClock.elapsedRealtime();
        if (now - lastUi >= 500) { lastUi = now; message(text); }
    }

    private void render(Image image, FrameMath.Plane luma, FrameMath.Box face, long token) {
        int w = 320, h = Math.max(1, image.getHeight() * w / image.getWidth());
        int[] pixels = new int[w * h];
        // A deliberately ordinary CPU preview avoids the protected MiSecureCamera/EGL path.
        Image.Plane u = image.getPlanes()[1], v = image.getPlanes()[2];
        FrameMath.Plane chromaU = new FrameMath.Plane(u.getBuffer(), u.getRowStride(), u.getPixelStride(),
                (image.getWidth() + 1) / 2, (image.getHeight() + 1) / 2);
        FrameMath.Plane chromaV = new FrameMath.Plane(v.getBuffer(), v.getRowStride(), v.getPixelStride(),
                (image.getWidth() + 1) / 2, (image.getHeight() + 1) / 2);
        for (int py = 0; py < h; py++) for (int px = 0; px < w; px++) {
            int x = px * image.getWidth() / w, y = py * image.getHeight() / h;
            int yy = Math.max(0, luma.at(x, y) - 16), uu = chromaU.at(x / 2, y / 2) - 128;
            int vv = chromaV.at(x / 2, y / 2) - 128;
            pixels[py*w+px] = Color.rgb(clamp((298*yy + 409*vv + 128) >> 8),
                    clamp((298*yy - 100*uu - 208*vv + 128) >> 8),
                    clamp((298*yy + 516*uu + 128) >> 8));
        }
        Bitmap frame = Bitmap.createBitmap(pixels, w, h, Bitmap.Config.ARGB_8888);
        Arrays.fill(pixels, 0);
        RectF bounds = face == null ? null : new RectF((float)(face.left*w/image.getWidth()),
                (float)(face.top*h/image.getHeight()), (float)(face.right*w/image.getWidth()),
                (float)(face.bottom*h/image.getHeight()));
        int degrees = orientation;
        runOnUiThread(() -> {
            if (current(token)) preview.update(frame, bounds, degrees); else frame.recycle();
        });
    }
    private static int clamp(int value) { return Math.max(0, Math.min(255, value)); }

    private final class Preview extends View {
        private Bitmap bitmap;
        private RectF face;
        private int degrees;
        private final Paint paint = new Paint(Paint.FILTER_BITMAP_FLAG | Paint.ANTI_ALIAS_FLAG);
        Preview() {
            super(FaceLabActivity.this);
            // Draw into a software layer so recycled frame bitmaps cannot remain in display lists.
            setLayerType(View.LAYER_TYPE_SOFTWARE, null);
        }
        void update(Bitmap next, RectF bounds, int orientation) {
            clear(); bitmap = next; face = bounds; degrees = orientation; invalidate();
        }
        void clear() {
            if (bitmap != null) { bitmap.recycle(); bitmap = null; }
            face = null; invalidate();
        }
        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas); canvas.drawColor(Color.BLACK);
            if (bitmap == null || bitmap.isRecycled()) return;
            Matrix transform = new Matrix();
            transform.postTranslate(-bitmap.getWidth()/2f, -bitmap.getHeight()/2f);
            transform.postRotate(degrees);
            // Mirror only the displayed image; analysis is kept in sensor coordinates.
            transform.postScale(-1, 1);
            int rotatedWidth = degrees % 180 == 0 ? bitmap.getWidth() : bitmap.getHeight();
            int rotatedHeight = degrees % 180 == 0 ? bitmap.getHeight() : bitmap.getWidth();
            float scale = Math.min((float)getWidth()/rotatedWidth, (float)getHeight()/rotatedHeight);
            transform.postScale(scale, scale); transform.postTranslate(getWidth()/2f, getHeight()/2f);
            canvas.drawBitmap(bitmap, transform, paint);
            if (face != null) {
                RectF bounds = new RectF(face); transform.mapRect(bounds);
                paint.setStyle(Paint.Style.STROKE); paint.setColor(Color.GREEN); paint.setStrokeWidth(3);
                canvas.drawRect(bounds, paint); paint.setStyle(Paint.Style.FILL);
            }
        }
    }
}
