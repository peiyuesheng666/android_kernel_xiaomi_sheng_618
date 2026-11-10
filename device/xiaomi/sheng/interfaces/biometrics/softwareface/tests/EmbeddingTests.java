// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.facelab;

import java.util.Arrays;

public final class EmbeddingTests {
    private static void rejects(Runnable action) {
        try { action.run(); } catch (IllegalArgumentException expected) { return; }
        throw new AssertionError("invalid feature accepted");
    }
    public static void main(String[] args) {
        float[] raw = new float[128]; raw[0] = 3; raw[1] = 4;
        float[] a = FaceEmbedding.normalized(raw);
        if (Math.abs(a[0] - .6) > 1e-6 || Math.abs(a[1] - .8) > 1e-6) throw new AssertionError();
        float[] opposite = a.clone(); for (int i=0;i<128;i++) opposite[i] = -opposite[i];
        if (Math.abs(FaceEmbedding.cosine(a,a)-1) > 1e-6 || Math.abs(FaceEmbedding.cosine(a,opposite)+1)>1e-6)
            throw new AssertionError("cosine orientation");
        rejects(() -> FaceEmbedding.normalized(new float[127]));
        rejects(() -> FaceEmbedding.normalized(new float[128]));
        raw[2] = Float.NaN; rejects(() -> FaceEmbedding.normalized(raw));
        raw[2] = Float.POSITIVE_INFINITY; rejects(() -> FaceEmbedding.normalized(raw));
        rejects(() -> FaceEmbedding.validate(new float[128]));
        SampleCollector c = new SampleCollector(FaceEmbedding::validate); long token = c.begin();
        for (int i=0;i<12;i++) if (!c.offer(token,i*SampleCollector.INTERVAL_NS,a)) throw new AssertionError();
        float[][] done = c.completed(token);
        if (done == null || done.length != 12 || c.completed(token) != null) throw new AssertionError();
        Arrays.fill(a,0); FaceEmbedding.validate(done[0]);
        token = c.begin(); c.cancel();
        if (c.offer(token,0,done[0])) throw new AssertionError("cancelled token reused");
        System.out.println("10 embedding/collector checks passed");
    }
}
