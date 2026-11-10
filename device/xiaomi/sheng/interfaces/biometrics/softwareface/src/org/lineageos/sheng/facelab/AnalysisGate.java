// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.facelab;

/** Only one inference owns copied pixels; camera callbacks keep draining newer frames. */
public final class AnalysisGate {
    private final long intervalNs;
    private boolean busy;
    private long lastTimestamp = -1;
    public AnalysisGate(long intervalNs) {
        if (intervalNs < 0) throw new IllegalArgumentException("Negative interval");
        this.intervalNs = intervalNs;
    }
    public synchronized boolean acquire(long timestamp) {
        if (busy || timestamp < 0 || (lastTimestamp >= 0 && timestamp-lastTimestamp < intervalNs)) return false;
        busy = true; lastTimestamp = timestamp; return true;
    }
    public synchronized void release() { busy = false; }
    public synchronized boolean busy() { return busy; }
    // A canceled inference still owns its pixels until its finally block releases them.
    public synchronized void resetTiming() { lastTimestamp = -1; }
}
