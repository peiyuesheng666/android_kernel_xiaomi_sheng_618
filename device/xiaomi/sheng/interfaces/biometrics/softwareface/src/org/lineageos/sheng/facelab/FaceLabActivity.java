// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.facelab;

import android.Manifest;
import android.app.Activity;
import android.app.KeyguardManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.graphics.SurfaceTexture;
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
import android.util.Range;
import android.view.Surface;
import android.view.View;
import android.view.TextureView;
import android.view.WindowManager;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.FrameLayout;

import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicLong;

/** User-operated development UI. Never registers a biometric sensor or unlocks the device. */
public final class FaceLabActivity extends Activity {
    private static final int CAMERA_PERMISSION = 10, CONFIRM_CREDENTIAL = 11;
    private final SampleCollector collector = new SampleCollector(FaceEmbedding::validate);
    private final AtomicLong epoch = new AtomicLong();
    private HandlerThread cameraThread;
    private Handler worker;
    private HandlerThread analysisThread;
    private Handler analyzer;
    private final AnalysisGate analysisGate = new AnalysisGate(100_000_000L);
    private final AtomicLong displayedFrames = new AtomicLong();
    private TextView status;
    private TextView guidanceView;
    private TextView performanceView;
    private Preview preview;
    private TemplateStore store;
    // Camera resources, descriptors and capture state are confined to worker.
    // Native inference runs on analyzer; AnalysisGate excludes engine self-tests.
    private CameraDevice camera;
    private CameraCaptureSession session;
    private ImageReader reader;
    private Surface previewSurface;
    private OpenCvEngine engine;
    private float[][] enrolled;
    private boolean comparing;
    private long lastUi, enrollmentDeadline, purpose;
    private long statsStart, receivedFrames, analyzedFrames, priorDisplayed, analysisTime, copyTime;
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
        analysisThread = new HandlerThread("ShengFaceLab-analysis"); analysisThread.start();
        analyzer = new Handler(analysisThread.getLooper());
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
        status = new TextView(this); status.setTextSize(18); root.addView(status);
        guidanceView = new TextView(this); guidanceView.setTextSize(16); root.addView(guidanceView);
        performanceView = new TextView(this); performanceView.setTextSize(14); root.addView(performanceView);
        button(root, "开启前摄", this::requestCamera);
        button(root, "检查识别引擎（不打开前摄）", this::checkEngine);
        button(root, "录入样本（先验证锁屏密码）", this::requestEnrollment);
        button(root, "比较当前人脸", this::requestComparison);
        button(root, "停止前摄", this::stopCamera);
        button(root, "删除已录入样本", () -> {
            collector.cancel(); credentialDeadline = 0;
            worker.post(() -> {
                purpose++; comparing = false; wipeEnrolled();
                try { store.delete(); message("已删除样本及加密密钥"); }
                catch (Exception e) { message("删除未完成：" + e.getClass().getSimpleName()); }
            });
        });
        setContentView(root); root.requestApplyInsets(); message("前摄尚未开启");
        getSystemService(DisplayManager.class).registerDisplayListener(displayListener, new Handler(getMainLooper()));
        if (getIntent().getBooleanExtra("engine_self_test", false)) checkEngine();
    }

    private void checkEngine() {
        message("正在检查识别引擎，前摄保持关闭…");
        worker.post(() -> {
            if (cameraRequested || camera != null || analysisGate.busy()) { message("请先停止前摄并等待当前检测结束"); return; }
            try {
                if (engine == null) engine = new OpenCvEngine(this);
                engine.checkFeatureOutput();
                android.util.Log.i("ShengFaceLab", engine.benchmark());
                android.util.Log.i("ShengFaceLab", "Engine self-test passed; camera not opened");
                message("检测与识别引擎检查通过，前摄尚未开启");
            } catch (Exception | LinkageError failure) {
                android.util.Log.e("ShengFaceLab", "Engine self-test failed", failure);
                message("识别引擎检查失败：" + failure.getClass().getSimpleName());
            }
        });
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
        stopCamera(); worker.post(this::wipeEnrolled);
        analysisThread.quitSafely(); cameraThread.quitSafely(); super.onDestroy();
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
        if (!preview.available()) { message("预览区域正在准备，请稍后点击开启前摄"); return; }
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
        if (performanceView != null) performanceView.setText("");
        if (worker != null) worker.post(this::closeCamera);
        message("前摄已停止，未完成的采集已取消");
    }
    private void closeCamera() {
        purpose++; comparing = false; lastUi = 0; analysisGate.resetTiming();
        wipeEnrolled();
        if (session != null) { session.close(); session = null; }
        if (camera != null) { camera.close(); camera = null; }
        if (reader != null) { reader.close(); reader = null; }
        if (previewSurface != null) { previewSurface.release(); previewSurface = null; }
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
            if (engine == null) {
                message("正在加载已校验的检测和识别模型…");
                engine = new OpenCvEngine(this);
            }
            if (!current(token)) return;
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
            Size selected = null, selectedPreview = null; long best = Long.MAX_VALUE;
            if (map != null) for (Size size : map.getOutputSizes(ImageFormat.YUV_420_888)) {
                if (size.getWidth() < 320 || size.getHeight() < 240 || size.getWidth() > 1280 || size.getHeight() > 960) continue;
                for (Size display : map.getOutputSizes(SurfaceTexture.class)) {
                    if (display.getWidth() > 1920 || display.getHeight() > 1440
                            || display.getWidth() < 320 || display.getHeight() < 240
                            || (long)display.getWidth()*size.getHeight() != (long)display.getHeight()*size.getWidth()) continue;
                    long cost = sizeCost(size)*10+sizeCost(display);
                    if (cost < best) { best=cost; selected=size; selectedPreview=display; }
                }
            }
            if (selected == null) throw new IllegalStateException("Matching preview/YUV streams unavailable");
            reader = ImageReader.newInstance(selected.getWidth(), selected.getHeight(),
                    ImageFormat.YUV_420_888, 3);
            reader.setOnImageAvailableListener(r -> {
                if (!current(token)) return;
                try {
                    Image next = r.acquireLatestImage();
                    if (next == null) return;
                    receivedFrames++; statistics(token);
                    processImage(next, token);
                } catch (Exception e) { cameraFailure(token, "接收前摄帧失败：" + e.getClass().getSimpleName()); }
            }, worker);
            final String frontId=front;
            final Size displaySize=selectedPreview;
            final int rotation=orientation;
            final Range<Integer> fps=previewRate(characteristics.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES));
            runOnUiThread(() -> {
                if (!current(token)) return;
                try {
                    Surface target=preview.configure(displaySize,rotation);
                    if (!worker.post(() -> openDevice(token,frontId,target,disableRotateCrop,fps))) target.release();
                } catch (RuntimeException failure) {
                    worker.post(() -> cameraFailure(token,"预览区域已关闭，请重新开启前摄"));
                }
            });
        } catch (Exception | LinkageError e) {
            cameraFailure(token, "开启前摄或引擎失败：" + e.getClass().getSimpleName());
        }
    }
    private static Range<Integer> previewRate(Range<Integer>[] rates) {
        Range<Integer> result=null;
        if (rates != null) for (Range<Integer> rate : rates) {
            if (rate.getUpper()>30) continue;
            if (result == null || rate.getUpper()>result.getUpper()
                    || (rate.getUpper().equals(result.getUpper()) && rate.getLower()>result.getLower())) result=rate;
        }
        return result;
    }
    private void openDevice(long token, String front, Surface display, boolean disableRotateCrop, Range<Integer> fps) {
        if (!current(token)) { display.release(); return; }
        previewSurface=display;
        statsStart=SystemClock.elapsedRealtime(); receivedFrames=analyzedFrames=analysisTime=copyTime=0;
        priorDisplayed=displayedFrames.get();
        try {
            getSystemService(CameraManager.class).openCamera(front, new CameraDevice.StateCallback() {
                @Override public void onOpened(CameraDevice device) {
                    if (!current(token)) { device.close(); return; }
                    camera = device;
                    try {
                        Surface target = reader.getSurface();
                        device.createCaptureSession(Arrays.asList(target,display),
                                new CameraCaptureSession.StateCallback() {
                            @Override public void onConfigured(CameraCaptureSession configured) {
                                if (!current(token)) { configured.close(); return; }
                                session = configured;
                                try {
                                    CaptureRequest.Builder request = device.createCaptureRequest(
                                            CameraDevice.TEMPLATE_PREVIEW);
                                    request.addTarget(target);
                                    request.addTarget(display);
                                    request.set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO);
                                    request.set(CaptureRequest.STATISTICS_FACE_DETECT_MODE,
                                            CaptureRequest.STATISTICS_FACE_DETECT_MODE_OFF);
                                    if (fps != null) request.set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE,fps);
                                    if (disableRotateCrop && Build.VERSION.SDK_INT >= 31)
                                        request.set(CaptureRequest.SCALER_ROTATE_AND_CROP,
                                                CaptureRequest.SCALER_ROTATE_AND_CROP_NONE);
                                    configured.setRepeatingRequest(request.build(), null, worker);
                                    runOnUiThread(() -> { if (current(token)) preview.showStream(); });
                                    android.util.Log.i("ShengFaceLab","Preview stream="+preview.streamSizeText()
                                            +" YUV="+reader.getWidth()+"x"+reader.getHeight()+" FPS="+fps);
                                    message("前摄已开启，软件检测已就绪；请保持单人正脸入镜");
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
        } catch (Exception | LinkageError e) {
            cameraFailure(token, "开启前摄失败：" + e.getClass().getSimpleName());
        }
    }
    private static long sizeCost(Size size) {
        return Math.abs((long) size.getWidth() * size.getHeight() - 1280 * 960);
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
            credentialDeadline = 0; purpose++; comparing = false; long generation = collector.begin();
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
            purpose++; collector.cancel(); comparing = false; wipeEnrolled();
            try {
                enrolled = store.load(); comparing = enrolled != null && camera != null;
                message(enrolled == null ? "尚未录入样本" : camera == null
                        ? "请先开启前摄" : "正在比较，仅显示特征距离，不执行解锁");
            } catch (Exception e) { message("读取样本失败：" + e.getClass().getSimpleName()); }
        });
    }

    private void processImage(Image acquired, long token) {
        OpenCvEngine.Frame copied=null;
        long timestamp=0; boolean owned=false;
        try (Image image = acquired) {
            if (image == null || !current(token)) return;
            timestamp=image.getTimestamp();
            if (!analysisGate.acquire(timestamp)) return;
            owned=true; copied=OpenCvEngine.capture(image);
        } catch (Exception failure) {
            if (owned) analysisGate.release();
            if (copied != null) copied.clear();
            cameraFailure(token,"复制前摄帧失败："+failure.getClass().getSimpleName()); return;
        }
        // The camera Image is closed before native inference. Busy callbacks only drain and close.
        final OpenCvEngine.Frame frame=copied;
        final long frameTimestamp=timestamp, purposeToken=purpose, generation=collector.generation();
        final boolean extract=collector.wantsSample(timestamp) || comparing;
        final int frameRotation=orientation;
        final OpenCvEngine inference=engine;
        if (!analyzer.post(() -> {
            try {
                if (!current(token)) return;
                OpenCvEngine.Result result=inference.analyze(frame,frameRotation,extract);
                if (!worker.post(() -> acceptResult(result,token,purposeToken,generation,frameTimestamp))
                        && result.embedding != null) Arrays.fill(result.embedding,0);
            } catch (Exception | LinkageError failure) {
                worker.post(() -> cameraFailure(token,"检测前摄帧失败："+failure.getClass().getSimpleName()));
            } finally { frame.clear(); analysisGate.release(); }
        })) { frame.clear(); analysisGate.release(); }
    }
    private void acceptResult(OpenCvEngine.Result result, long token, long purposeToken, long generation, long timestamp) {
        float[] descriptor=result.embedding;
        try {
            if (!current(token)) return;
            analyzedFrames++; analysisTime+=result.analysisNs; copyTime+=result.copyNs;
            runOnUiThread(() -> {
                if (current(token)) preview.update(result.face,result.width,result.height);
            });
            if (purposeToken != purpose) return;
            if (collector.collecting() && SystemClock.elapsedRealtime() >= enrollmentDeadline) {
                collector.cancel(); message("采集超时，未修改原有样本"); return;
            }
            String guidance=result.guidance;
            if (descriptor != null && collector.collecting()) {
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
            } else if (descriptor != null && comparing && enrolled != null) {
                double sum = 0;
                for (float[] sample : enrolled) sum += FaceEmbedding.cosine(descriptor, sample);
                guidance=String.format(Locale.ROOT, "平均余弦相似度 %.4f（越高越相似）\n测试结果，不执行解锁", sum / enrolled.length);
            }
            periodic(token,guidance);
        } catch (Exception e) { cameraFailure(token, "处理检测结果失败：" + e.getClass().getSimpleName()); }
        finally { if (descriptor != null) Arrays.fill(descriptor,0); }
    }
    private void periodic(long token, String text) {
        long now = SystemClock.elapsedRealtime();
        if (now - lastUi >= 500) {
            lastUi = now;
            String prefix = collector.collecting() ? "当前采集 " + collector.count() + "/12：" : "";
            runOnUiThread(() -> { if (current(token)) guidanceView.setText(prefix+text); });
        }
    }
    private void statistics(long token) {
        long now=SystemClock.elapsedRealtime(), elapsed=now-statsStart;
        if (elapsed<2000) return;
        double seconds=elapsed/1000.0;
        long shown=displayedFrames.get();
        String text=String.format(Locale.ROOT,"预览 %.1f 帧/秒 · 检测 %.1f 次/秒",
                (shown-priorDisplayed)/seconds,analyzedFrames/seconds);
        android.util.Log.i("ShengFaceLab",String.format(Locale.ROOT,
                "Pipeline preview_fps=%.2f received_fps=%.2f analyzed_fps=%.2f copy_ms=%.2f analysis_ms=%.2f",
                (shown-priorDisplayed)/seconds,receivedFrames/seconds,analyzedFrames/seconds,
                analyzedFrames==0?0:copyTime/1e6/analyzedFrames,analyzedFrames==0?0:analysisTime/1e6/analyzedFrames));
        runOnUiThread(() -> { if (current(token)) performanceView.setText(text); });
        statsStart=now; priorDisplayed=shown; receivedFrames=analyzedFrames=analysisTime=copyTime=0;
    }

    private final class Preview extends FrameLayout {
        private final TextureView texture;
        private final View shutter;
        private final FaceOverlay overlay;
        private volatile Size stream;
        private int degrees;
        Preview() {
            super(FaceLabActivity.this);
            setBackgroundColor(Color.BLACK);
            texture=new TextureView(FaceLabActivity.this);
            addView(texture,new FrameLayout.LayoutParams(-1,-1));
            shutter=new View(FaceLabActivity.this); shutter.setBackgroundColor(Color.BLACK);
            addView(shutter,new FrameLayout.LayoutParams(-1,-1));
            overlay=new FaceOverlay(); addView(overlay,new FrameLayout.LayoutParams(-1,-1));
            texture.setSurfaceTextureListener(new TextureView.SurfaceTextureListener() {
                @Override public void onSurfaceTextureAvailable(SurfaceTexture surface,int width,int height) { transform(); }
                @Override public void onSurfaceTextureSizeChanged(SurfaceTexture surface,int width,int height) { transform(); }
                @Override public boolean onSurfaceTextureDestroyed(SurfaceTexture surface) {
                    if (cameraRequested) stopCamera(); return true;
                }
                @Override public void onSurfaceTextureUpdated(SurfaceTexture surface) {
                    if (resumed && cameraRequested) displayedFrames.incrementAndGet();
                }
            });
        }
        boolean available() { return texture.isAvailable(); }
        String streamSizeText() { Size size=stream; return size==null?"unknown":size.toString(); }
        Surface configure(Size size,int orientation) {
            SurfaceTexture surface=texture.getSurfaceTexture();
            if (surface==null) throw new IllegalStateException("Preview surface unavailable");
            stream=size; degrees=orientation;
            surface.setDefaultBufferSize(size.getWidth(),size.getHeight()); transform();
            return new Surface(surface);
        }
        void showStream() { shutter.setVisibility(View.GONE); }
        void update(RectF bounds,int width,int height) { overlay.update(bounds,width,height); }
        void clear() {
            shutter.setVisibility(View.VISIBLE); overlay.update(null,0,0);
        }
        @Override protected void onSizeChanged(int w,int h,int oldw,int oldh) {
            super.onSizeChanged(w,h,oldw,oldh); transform();
        }
        private void transform() {
            Size size=stream;
            if (size==null || getWidth()==0 || getHeight()==0) return;
            Matrix matrix=new Matrix();
            matrix.setValues(PreviewGeometry.texture(size.getWidth(),size.getHeight(),degrees,getWidth(),getHeight()));
            texture.setTransform(matrix); overlay.invalidate();
        }
        private final class FaceOverlay extends View {
            private RectF face;
            private int width,height;
            private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
            FaceOverlay() {
                super(FaceLabActivity.this);
                paint.setStyle(Paint.Style.STROKE); paint.setColor(Color.GREEN);
                paint.setStrokeWidth(3*getResources().getDisplayMetrics().density);
            }
            void update(RectF bounds,int width,int height) {
                face=bounds==null?null:new RectF(bounds); this.width=width; this.height=height; invalidate();
            }
            @Override protected void onDraw(Canvas canvas) {
                super.onDraw(canvas);
                if (face==null || width==0 || height==0 || getWidth()==0 || getHeight()==0) return;
                Matrix matrix=new Matrix();
                matrix.setValues(PreviewGeometry.sensor(width,height,0,getWidth(),getHeight()));
                RectF bounds=new RectF(face); matrix.mapRect(bounds); canvas.drawRect(bounds,paint);
            }
        }
    }
}
