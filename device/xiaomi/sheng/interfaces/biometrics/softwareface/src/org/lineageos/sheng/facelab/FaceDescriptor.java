// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.facelab;

/** Locally written spatial uniform-LBP experiment. It makes no authentication decision. */
public final class FaceDescriptor {
    public static final int SIZE = 96, CELLS = 8, BINS = 59;
    public static final int LENGTH = CELLS * CELLS * BINS;
    private static final int[] LABEL = labels();
    private FaceDescriptor() {}

    private static int[] labels() {
        int[] labels = new int[256];
        int next = 0;
        for (int value = 0; value < 256; value++) {
            int changes = Integer.bitCount((value ^ ((value << 1) | (value >>> 7))) & 255);
            labels[value] = changes <= 2 ? next++ : BINS - 1;
        }
        if (next != BINS - 1) throw new AssertionError("Uniform-LBP bin count");
        return labels;
    }

    public static final class Quality {
        public final double mean, contrast, edgeEnergy;
        Quality(double mean, double contrast, double edgeEnergy) {
            this.mean = mean; this.contrast = contrast; this.edgeEnergy = edgeEnergy;
        }
        public boolean usable() {
            // Development capture filters only; these are not calibrated identity thresholds.
            return mean >= 35 && mean <= 220 && contrast >= 12 && edgeEnergy >= 3;
        }
    }

    private static void check(byte[] pixels) {
        if (pixels.length != SIZE * SIZE) throw new IllegalArgumentException("Wrong face size");
    }

    public static Quality quality(byte[] pixels) {
        check(pixels);
        double sum = 0, squared = 0, edges = 0;
        for (int y = 0; y < SIZE; y++) for (int x = 0; x < SIZE; x++) {
            int p = pixels[y * SIZE + x] & 255;
            sum += p; squared += p * p;
            if (x > 0 && y > 0) {
                edges += Math.abs(p - (pixels[y * SIZE + x - 1] & 255));
                edges += Math.abs(p - (pixels[(y - 1) * SIZE + x] & 255));
            }
        }
        double mean = sum / pixels.length;
        return new Quality(mean, Math.sqrt(Math.max(0, squared / pixels.length - mean * mean)),
                edges / (2 * (SIZE - 1) * (SIZE - 1)));
    }

    public static float[] extract(byte[] pixels) {
        check(pixels);
        float[] histogram = new float[LENGTH];
        int[] counts = new int[CELLS * CELLS];
        for (int y = 1; y < SIZE - 1; y++) for (int x = 1; x < SIZE - 1; x++) {
            int c = pixels[y * SIZE + x] & 255, code = 0;
            if ((pixels[(y-1)*SIZE+x-1] & 255) >= c) code |= 1;
            if ((pixels[(y-1)*SIZE+x] & 255) >= c) code |= 2;
            if ((pixels[(y-1)*SIZE+x+1] & 255) >= c) code |= 4;
            if ((pixels[y*SIZE+x+1] & 255) >= c) code |= 8;
            if ((pixels[(y+1)*SIZE+x+1] & 255) >= c) code |= 16;
            if ((pixels[(y+1)*SIZE+x] & 255) >= c) code |= 32;
            if ((pixels[(y+1)*SIZE+x-1] & 255) >= c) code |= 64;
            if ((pixels[y*SIZE+x-1] & 255) >= c) code |= 128;
            int cell = (y * CELLS / SIZE) * CELLS + x * CELLS / SIZE;
            histogram[cell * BINS + LABEL[code]]++;
            counts[cell]++;
        }
        for (int i = 0; i < LENGTH; i++) histogram[i] /= counts[i / BINS];
        return histogram;
    }

    public static void validate(float[] descriptor) {
        if (descriptor.length != LENGTH) throw new IllegalArgumentException("Wrong descriptor size");
        for (int cell = 0; cell < CELLS * CELLS; cell++) {
            double total = 0;
            for (int b = 0; b < BINS; b++) {
                float f = descriptor[cell * BINS + b];
                if (!Float.isFinite(f) || f < 0 || f > 1)
                    throw new IllegalArgumentException("Invalid descriptor value");
                total += f;
            }
            if (Math.abs(total - 1) > .001) throw new IllegalArgumentException("Unnormalized cell");
        }
    }

    /** Mean Hellinger distance, 0..1. No unvalidated accept/reject cutoff. */
    public static double distance(float[] a, float[] b) {
        validate(a); validate(b);
        double sum = 0;
        for (int i = 0; i < LENGTH; i++) {
            double difference = Math.sqrt(a[i]) - Math.sqrt(b[i]);
            sum += difference * difference;
        }
        return Math.sqrt(Math.max(0, Math.min(1, sum / (2 * CELLS * CELLS))));
    }
}
