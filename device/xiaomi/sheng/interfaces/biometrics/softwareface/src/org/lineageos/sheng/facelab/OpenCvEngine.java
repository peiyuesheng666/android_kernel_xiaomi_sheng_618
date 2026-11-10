// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.facelab;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.RectF;
import android.media.Image;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Locale;
import org.opencv.android.Utils;
import org.opencv.core.Core;
import org.opencv.core.CvType;
import org.opencv.core.Mat;
import org.opencv.core.MatOfDouble;
import org.opencv.core.Size;
import org.opencv.imgproc.Imgproc;
import org.opencv.objdetect.FaceDetectorYN;
import org.opencv.objdetect.FaceRecognizerSF;

/** Source-owned adapter. Dependencies and their unmodified licenses are separately inventoried. */
final class OpenCvEngine {
    private static final String YUNET = "face_detection_yunet_2023mar.onnx";
    private static final String SFACE = "face_recognition_sface_2021dec.onnx";
    private static final String YUNET_SHA = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4";
    private static final String SFACE_SHA = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79";
    private final FaceDetectorYN detector;
    private final FaceRecognizerSF recognizer;

    OpenCvEngine(Context context) throws Exception {
        System.loadLibrary("opencv_java4");
        if (!Core.VERSION.equals("4.13.0")) throw new IllegalStateException("Unreviewed OpenCV runtime");
        Core.setNumThreads(2);
        File detection = model(context, YUNET, YUNET_SHA), recognition = model(context, SFACE, SFACE_SHA);
        detector = FaceDetectorYN.create(detection.getPath(), "", new Size(640, 480), .85f, .3f, 500);
        recognizer = FaceRecognizerSF.create(recognition.getPath(), "");
        // Exercise model loading/inference without a camera or any personal image.
        Mat blank = Mat.zeros(480, 640, CvType.CV_8UC3), faces = new Mat();
        try { detector.detect(blank, faces); }
        finally { faces.release(); blank.release(); }
    }

    void checkFeatureOutput() {
        Mat blank = Mat.zeros(112,112,CvType.CV_8UC3), feature = new Mat();
        float[] values = new float[FaceEmbedding.LENGTH];
        float[] normalized = null;
        try {
            recognizer.feature(blank,feature);
            if (feature.total() != FaceEmbedding.LENGTH || feature.type() != CvType.CV_32FC1)
                throw new IllegalStateException("Unexpected engine output");
            feature.get(0,0,values);
            normalized = FaceEmbedding.normalized(values);
        } finally {
            Arrays.fill(values,0);
            if (normalized != null) Arrays.fill(normalized,0);
            feature.release(); blank.release();
        }
    }

    private static File model(Context context, String name, String expected) throws Exception {
        File result = new File(context.getNoBackupFilesDir(), name);
        // Recreate from the APK, not a writable external model path.
        File temp = new File(context.getNoBackupFilesDir(), name + ".new");
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = context.getAssets().open("models/" + name);
                FileOutputStream output = new FileOutputStream(temp)) {
            byte[] block = new byte[16384]; int count;
            while ((count = input.read(block)) != -1) {
                digest.update(block, 0, count); output.write(block, 0, count);
            }
            output.getFD().sync();
        }
        StringBuilder hex = new StringBuilder();
        for (byte value : digest.digest()) hex.append(String.format(Locale.ROOT, "%02x", value & 255));
        if (!expected.equals(hex.toString())) { temp.delete(); throw new IllegalStateException("Model checksum mismatch"); }
        if (!temp.renameTo(result)) { temp.delete(); throw new IllegalStateException("Model cache update failed"); }
        return result;
    }

    static final class Result {
        final Bitmap preview;
        final RectF face;
        final String guidance;
        final float[] embedding;
        Result(Bitmap preview, RectF face, String guidance, float[] embedding) {
            this.preview = preview; this.face = face; this.guidance = guidance; this.embedding = embedding;
        }
    }

    Result analyze(Image image, int degrees, boolean extractFeature) {
        int w = image.getWidth(), h = image.getHeight();
        if ((w & 1) != 0 || (h & 1) != 0 || !image.getCropRect().equals(new android.graphics.Rect(0,0,w,h)))
            throw new IllegalArgumentException("Unsupported YUV geometry");
        Image.Plane[] planes = image.getPlanes();
        FrameMath.Plane y = plane(planes[0], w, h), u = plane(planes[1], w/2, h/2), v = plane(planes[2], w/2, h/2);
        byte[] nv21 = new byte[w*h*3/2];
        for (int row = 0; row < h; row++) for (int col = 0; col < w; col++) nv21[row*w+col] = (byte)y.at(col,row);
        int offset = w*h;
        for (int row = 0; row < h/2; row++) for (int col = 0; col < w/2; col++) {
            nv21[offset++] = (byte)v.at(col,row); nv21[offset++] = (byte)u.at(col,row);
        }
        Mat packed = new Mat(h*3/2,w,CvType.CV_8UC1), sensor = new Mat(), upright = new Mat();
        Mat small = new Mat(), found = new Mat(), aligned = new Mat(), feature = new Mat();
        Mat gray = new Mat(), laplacian = new Mat(), rgba = new Mat();
        MatOfDouble mean = new MatOfDouble(), deviation = new MatOfDouble();
        float[] embedding = null;
        Bitmap preview = null;
        try {
            packed.put(0,0,nv21); Imgproc.cvtColor(packed,sensor,Imgproc.COLOR_YUV2BGR_NV21);
            if (degrees == 0) sensor.copyTo(upright);
            else Core.rotate(sensor,upright,degrees == 90 ? Core.ROTATE_90_CLOCKWISE
                    : degrees == 180 ? Core.ROTATE_180 : Core.ROTATE_90_COUNTERCLOCKWISE);
            double scale = Math.min(1,640.0 / Math.max(upright.cols(),upright.rows()));
            Imgproc.resize(upright,small,new Size(Math.round(upright.cols()*scale),Math.round(upright.rows()*scale)));
            detector.setInputSize(small.size()); detector.detect(small,found);
            String guidance = found.rows() == 0 ? "未检测到人脸" : "请保持只有一张人脸入镜";
            RectF bounds = null;
            if (found.rows() == 1) {
                float[] row = new float[15]; found.get(0,0,row);
                double sx = (double)upright.cols()/small.cols(), sy = (double)upright.rows()/small.rows();
                for (int i = 0; i < 14; i++) row[i] *= (i % 2 == 0 ? sx : sy);
                bounds = new RectF(row[0],row[1],row[0]+row[2],row[1]+row[3]);
                boolean inside = bounds.left >= 0 && bounds.top >= 0 && bounds.right <= upright.cols()
                        && bounds.bottom <= upright.rows();
                boolean near = row[2]/sx >= 90 && row[3]/sy >= 90;
                guidance = !inside ? "请将整张脸移入画面" : !near ? "请将脸靠近一些" : "正脸已检测到";
                if (inside && near && extractFeature) {
                    Mat landmarks = new Mat(1,15,CvType.CV_32FC1);
                    try { landmarks.put(0,0,row); recognizer.alignCrop(upright,landmarks,aligned); }
                    finally { landmarks.release(); }
                    Imgproc.cvtColor(aligned,gray,Imgproc.COLOR_BGR2GRAY);
                    Core.meanStdDev(gray,mean,deviation);
                    double brightness = mean.toArray()[0], contrast = deviation.toArray()[0];
                    Imgproc.Laplacian(gray,laplacian,CvType.CV_32F);
                    Core.meanStdDev(laplacian,mean,deviation);
                    double sharpness = deviation.toArray()[0];
                    if (brightness < 35 || brightness > 220 || contrast < 12 || sharpness < 5) {
                        guidance = "请改善光线并保持正脸清晰";
                    } else {
                        recognizer.feature(aligned,feature);
                        if (feature.total() != FaceEmbedding.LENGTH || feature.type() != CvType.CV_32FC1)
                            throw new IllegalStateException("Unexpected engine output");
                        float[] raw = new float[FaceEmbedding.LENGTH];
                        try { feature.get(0,0,raw); embedding = FaceEmbedding.normalized(raw); }
                        finally { Arrays.fill(raw,0); }
                        guidance = "正脸质量可用";
                    }
                }
            }
            Imgproc.cvtColor(upright,rgba,Imgproc.COLOR_BGR2RGBA);
            preview = Bitmap.createBitmap(rgba.cols(),rgba.rows(),Bitmap.Config.ARGB_8888);
            Utils.matToBitmap(rgba,preview);
            return new Result(preview,bounds,guidance,embedding);
        } catch (RuntimeException failure) {
            if (preview != null) preview.recycle();
            if (embedding != null) Arrays.fill(embedding,0);
            throw failure;
        } finally {
            Arrays.fill(nv21,(byte)0);
            for (Mat m : new Mat[]{packed,sensor,upright,small,found,aligned,feature,gray,laplacian,rgba,mean,deviation}) m.release();
        }
    }

    private static FrameMath.Plane plane(Image.Plane p, int w, int h) {
        return new FrameMath.Plane(p.getBuffer(),p.getRowStride(),p.getPixelStride(),w,h);
    }
}
