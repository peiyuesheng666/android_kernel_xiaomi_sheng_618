// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.facelab;

/** Our representation and comparison rules for the pinned SFace engine output. */
public final class FaceEmbedding {
    public static final int LENGTH = 128;
    private FaceEmbedding() {}
    public static float[] normalized(float[] raw) {
        if (raw.length != LENGTH) throw new IllegalArgumentException("Unexpected embedding dimension");
        double squared = 0;
        for (float value : raw) {
            if (!Float.isFinite(value)) throw new IllegalArgumentException("Non-finite embedding");
            squared += (double) value * value;
        }
        if (squared < 1e-12) throw new IllegalArgumentException("Empty embedding");
        float[] result = new float[LENGTH];
        double norm = Math.sqrt(squared);
        for (int i = 0; i < LENGTH; i++) result[i] = (float) (raw[i] / norm);
        validate(result); return result;
    }
    public static void validate(float[] value) {
        if (value.length != LENGTH) throw new IllegalArgumentException("Unexpected embedding dimension");
        double squared = 0;
        for (float f : value) {
            if (!Float.isFinite(f)) throw new IllegalArgumentException("Non-finite embedding");
            squared += (double) f * f;
        }
        if (Math.abs(squared - 1) > .001) throw new IllegalArgumentException("Unnormalized embedding");
    }
    /** A displayed measurement only. There is no accept/reject threshold in this lab. */
    public static double cosine(float[] a, float[] b) {
        validate(a); validate(b);
        double dot = 0;
        for (int i = 0; i < LENGTH; i++) dot += (double) a[i] * b[i];
        return Math.max(-1, Math.min(1, dot));
    }
}
