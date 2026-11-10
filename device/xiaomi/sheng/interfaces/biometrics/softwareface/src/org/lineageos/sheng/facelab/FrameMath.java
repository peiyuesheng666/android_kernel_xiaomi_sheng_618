// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.facelab;

import java.nio.ByteBuffer;
import java.util.Arrays;

/** Camera-plane and coordinate operations, independent of Android and testable on the host. */
public final class FrameMath {
    private FrameMath() {}

    public static final class Box {
        public final double left, top, right, bottom;
        public Box(double left, double top, double right, double bottom) {
            if (!Double.isFinite(left) || !Double.isFinite(top) || !Double.isFinite(right)
                    || !Double.isFinite(bottom) || right <= left || bottom <= top) {
                throw new IllegalArgumentException("Invalid rectangle");
            }
            this.left = left; this.top = top; this.right = right; this.bottom = bottom;
        }
        public double width() { return right - left; }
        public double height() { return bottom - top; }
    }

    /** Camera2 crops the sensor region to the requested stream's aspect ratio. */
    public static Box streamCrop(Box sensorCrop, int width, int height) {
        if (width <= 0 || height <= 0) throw new IllegalArgumentException("Invalid stream");
        double w = sensorCrop.width(), h = sensorCrop.height(), ratio = (double) width / height;
        if (w / h > ratio) w = h * ratio; else h = w / ratio;
        double x = (sensorCrop.left + sensorCrop.right - w) / 2;
        double y = (sensorCrop.top + sensorCrop.bottom - h) / 2;
        return new Box(x, y, x + w, y + h);
    }

    /** Return null for partially clipped faces, rather than clamp and enroll background. */
    public static Box toStream(Box face, Box crop, int width, int height) {
        if (width <= 0 || height <= 0) throw new IllegalArgumentException("Invalid stream");
        if (face.left < crop.left || face.top < crop.top || face.right > crop.right
                || face.bottom > crop.bottom) return null;
        return new Box((face.left - crop.left) * width / crop.width(),
                (face.top - crop.top) * height / crop.height(),
                (face.right - crop.left) * width / crop.width(),
                (face.bottom - crop.top) * height / crop.height());
    }

    public static int rotation(int sensorDegrees, int displayDegrees) {
        // Clockwise rotation for our pixel sampler/Canvas. Camera2 expresses the
        // front sensor's relative rotation counterclockwise, hence this sign.
        int angle = Math.floorMod(displayDegrees - sensorDegrees, 360);
        if (angle % 90 != 0) throw new IllegalArgumentException("Non-cardinal rotation");
        return angle;
    }

    /** Copy camera rows in bulk, preserving plane offsets and padded/interleaved layouts. */
    public static byte[] nv21(Plane y, Plane u, Plane v) {
        if ((y.width & 1) != 0 || (y.height & 1) != 0
                || u.width != y.width/2 || v.width != u.width
                || u.height != y.height/2 || v.height != u.height
                || (long)y.width*y.height*3/2 > Integer.MAX_VALUE)
            throw new IllegalArgumentException("Invalid YUV planes");
        byte[] result = new byte[(int)((long)y.width*y.height*3/2)];
        int span = Math.max((y.width-1)*y.pixelStride+1,
                Math.max((u.width-1)*u.pixelStride+1, (v.width-1)*v.pixelStride+1));
        byte[] scratch = new byte[span];
        try {
            y.copyRows(result, 0, y.width, 1, scratch);
            v.copyRows(result, y.width*y.height, y.width, 2, scratch);
            u.copyRows(result, y.width*y.height+1, y.width, 2, scratch);
            return result;
        } catch (RuntimeException failure) {
            Arrays.fill(result, (byte)0); throw failure;
        } finally { Arrays.fill(scratch, (byte)0); }
    }

    public static final class Plane {
        private final ByteBuffer bytes;
        private final int rowStride, pixelStride, width, height, origin;
        public Plane(ByteBuffer bytes, int rowStride, int pixelStride, int width, int height) {
            if (width <= 0 || height <= 0 || rowStride <= 0 || pixelStride <= 0
                    || (long) (width - 1) * pixelStride + 1 > rowStride
                    || (long) (height - 1) * rowStride + (long) (width - 1) * pixelStride
                            >= bytes.remaining()) {
                throw new IllegalArgumentException("Truncated or invalid camera plane");
            }
            this.bytes = bytes.duplicate(); this.origin = bytes.position();
            this.rowStride = rowStride; this.pixelStride = pixelStride;
            this.width = width; this.height = height;
        }
        public int at(int x, int y) {
            if (x < 0 || y < 0 || x >= width || y >= height)
                throw new IllegalArgumentException("Pixel outside plane");
            return bytes.get(origin + y * rowStride + x * pixelStride) & 255;
        }
        private void copyRows(byte[] target, int offset, int targetRow, int step, byte[] scratch) {
            ByteBuffer source = bytes.duplicate();
            int span = (width-1)*pixelStride+1;
            for (int row = 0; row < height; row++) {
                source.position(origin+row*rowStride);
                int destination = offset+row*targetRow;
                if (pixelStride == 1 && step == 1) source.get(target, destination, width);
                else {
                    source.get(scratch, 0, span);
                    for (int col = 0; col < width; col++) target[destination+col*step] = scratch[col*pixelStride];
                }
            }
        }
        public byte[] normalized(Box region, int size, int degrees) {
            if (size < 2 || size > 1024 || region.left < 0 || region.top < 0
                    || region.right > width || region.bottom > height
                    || degrees < 0 || degrees >= 360 || degrees % 90 != 0) {
                throw new IllegalArgumentException("Invalid face crop");
            }
            byte[] result = new byte[size * size];
            for (int y = 0; y < size; y++) for (int x = 0; x < size; x++) {
                double u = (x + .5) / size, v = (y + .5) / size;
                double a = u, b = v;
                if (degrees == 90) { a = v; b = 1 - u; }
                if (degrees == 180) { a = 1 - u; b = 1 - v; }
                if (degrees == 270) { a = 1 - v; b = u; }
                int px = Math.min(width - 1, (int) (region.left + a * region.width()));
                int py = Math.min(height - 1, (int) (region.top + b * region.height()));
                result[y * size + x] = (byte) at(px, py);
            }
            return result;
        }
    }
}
