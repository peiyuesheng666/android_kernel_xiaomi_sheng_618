// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.facelab;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Generation tokens prevent delayed camera callbacks from entering a later enrollment. */
public final class SampleCollector {
    public static final int REQUIRED = 12;
    public static final long INTERVAL_NS = 250_000_000L;
    private long generation, lastTimestamp = -1;
    private boolean collecting;
    private final List<float[]> samples = new ArrayList<>();

    public synchronized long begin() {
        clear(); collecting = true; return ++generation;
    }
    public synchronized void cancel() { collecting = false; generation++; clear(); }
    public synchronized long generation() { return generation; }
    public synchronized int count() { return samples.size(); }
    public synchronized boolean collecting() { return collecting; }
    private void clear() {
        for (float[] sample : samples) Arrays.fill(sample, 0);
        samples.clear(); lastTimestamp = -1;
    }
    public synchronized boolean offer(long token, long timestamp, float[] descriptor) {
        if (!collecting || token != generation || timestamp < 0
                || (lastTimestamp >= 0 && timestamp - lastTimestamp < INTERVAL_NS)) return false;
        FaceDescriptor.validate(descriptor);
        samples.add(descriptor.clone()); lastTimestamp = timestamp;
        if (samples.size() == REQUIRED) collecting = false;
        return true;
    }
    public synchronized float[][] completed(long token) {
        if (token != generation || collecting || samples.size() != REQUIRED) return null;
        float[][] result = samples.stream().map(float[]::clone).toArray(float[][]::new);
        clear(); generation++;
        return result;
    }
}
