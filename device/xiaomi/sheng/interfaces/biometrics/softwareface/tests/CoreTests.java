// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.facelab;

import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.Random;

/** Synthetic input only. Passing these tests does not establish identity accuracy or liveness. */
public final class CoreTests {
    private static int checks;
    private static void check(boolean result, String detail) {
        checks++;
        if (!result) throw new AssertionError(detail);
    }
    private static void close(double a, double b, String detail) {
        check(Math.abs(a - b) < 1e-6, detail + ": " + a + " != " + b);
    }
    private static void rejects(Runnable action, String detail) {
        boolean rejected = false;
        try { action.run(); } catch (IllegalArgumentException expected) { rejected = true; }
        check(rejected, detail);
    }

    public static void main(String[] args) {
        ByteBuffer padded = ByteBuffer.wrap(new byte[]{99, 1, 99, 2, 99, 99, 3, 99, 4});
        padded.position(1);
        FrameMath.Plane plane = new FrameMath.Plane(padded, 5, 2, 2, 2);
        check(plane.at(0, 0) == 1 && plane.at(1, 0) == 2
                && plane.at(0, 1) == 3 && plane.at(1, 1) == 4, "Plane offset/strides");
        check(padded.position() == 1, "Source plane position preserved");
        FrameMath.Box full = new FrameMath.Box(0, 0, 2, 2);
        check(Arrays.equals(plane.normalized(full, 2, 0), new byte[]{1,2,3,4}), "0 degrees");
        check(Arrays.equals(plane.normalized(full, 2, 90), new byte[]{3,1,4,2}), "90 degrees");
        check(Arrays.equals(plane.normalized(full, 2, 180), new byte[]{4,3,2,1}), "180 degrees");
        check(Arrays.equals(plane.normalized(full, 2, 270), new byte[]{2,4,1,3}), "270 degrees");
        rejects(() -> new FrameMath.Plane(ByteBuffer.allocate(3), 2, 1, 2, 2), "Truncated plane");
        rejects(() -> new FrameMath.Plane(ByteBuffer.allocate(8), 1, 1, 2, 2), "Overlapping rows");
        rejects(() -> plane.at(-1, 0), "Out-of-plane pixel");
        rejects(() -> plane.normalized(full, 2, -90), "Invalid crop rotation");
        rejects(() -> new FrameMath.Box(Double.NaN, 0, 2, 2), "NaN rectangle");
        FrameMath.Box crop = FrameMath.streamCrop(new FrameMath.Box(10, 20, 4010, 3020), 1920, 1080);
        close(crop.left, 10, "Sensor crop left"); close(crop.top, 395, "Sensor crop top");
        close(crop.bottom, 2645, "Sensor crop bottom");
        FrameMath.Box mapped = FrameMath.toStream(new FrameMath.Box(1010, 1145, 2010, 1895), crop, 1920, 1080);
        close(mapped.left, 480, "Face sensor->stream X");
        close(mapped.top, 360, "Face sensor->stream Y");
        close(mapped.width(), 480, "Face width");
        check(FrameMath.toStream(new FrameMath.Box(0, 0, 2000, 2000), crop, 1920,1080) == null,
                "Clipped face rejected");
        check(FrameMath.rotation(270, 90) == 180 && FrameMath.rotation(0, 270) == 270
                && FrameMath.rotation(270, 0) == 90 && FrameMath.rotation(0, 90) == 90,
                "Front camera/display rotations");
        rejects(() -> FrameMath.rotation(13, 0), "Invalid sensor rotation");

        byte[] face = new byte[96 * 96], unrelated = new byte[face.length], brighter = new byte[face.length];
        Random first = new Random(12), second = new Random(98);
        for (int i = 0; i < face.length; i++) {
            face[i] = (byte) (50 + first.nextInt(140));
            brighter[i] = (byte) ((face[i] & 255) + 20);
            unrelated[i] = (byte) (50 + second.nextInt(140));
        }
        check(FaceDescriptor.quality(face).usable(), "Textured synthetic crop capture quality");
        byte[] flat = new byte[face.length]; Arrays.fill(flat, (byte) 128);
        check(!FaceDescriptor.quality(flat).usable(), "Flat crop quality rejection");
        check(!FaceDescriptor.quality(new byte[face.length]).usable(), "Dark crop rejection");
        float[] descriptor = FaceDescriptor.extract(face), other = FaceDescriptor.extract(unrelated);
        close(FaceDescriptor.distance(descriptor, descriptor), 0, "Self distance");
        close(FaceDescriptor.distance(descriptor, FaceDescriptor.extract(brighter)), 0,
                "Nonclipping brightness invariance");
        double distance = FaceDescriptor.distance(descriptor, other);
        check(distance > 0 && distance <= 1, "Nonidentical synthetic crops have bounded distance");
        close(distance, FaceDescriptor.distance(other, descriptor), "Distance symmetry");
        float[] bad = descriptor.clone(); bad[0] = Float.NaN;
        rejects(() -> FaceDescriptor.distance(descriptor, bad), "NaN descriptor rejection");
        rejects(() -> FaceDescriptor.validate(new float[FaceDescriptor.LENGTH]), "Empty distribution");
        rejects(() -> FaceDescriptor.extract(new byte[95]), "Wrong crop size");

        SampleCollector collector = new SampleCollector();
        long old = collector.begin(); collector.cancel();
        long token = collector.begin();
        check(!collector.offer(old, 1, descriptor), "Canceled callback rejected in new enrollment");
        check(!collector.offer(token, -1, descriptor), "Invalid timestamp");
        check(collector.offer(token, 1, descriptor), "First sample accepted");
        check(!collector.offer(token, 1, descriptor), "Repeated frame rejected");
        check(!collector.offer(token, 1 + SampleCollector.INTERVAL_NS - 1, descriptor), "Too-close frame rejected");
        check(collector.completed(token) == null, "Partial enrollment never completes");
        float saved = descriptor[0]; descriptor[0] = Float.NaN;
        for (int i = 1; i < SampleCollector.REQUIRED; i++)
            check(collector.offer(token, 1 + i * SampleCollector.INTERVAL_NS, other), "Sample " + i);
        check(!collector.offer(token, 9_000_000_000L, other), "Completed enrollment rejects extra frames");
        float[][] complete = collector.completed(token);
        check(complete != null && complete.length == 12 && complete[0][0] == saved,
                "Sample inputs copied before caller reuse");
        check(collector.completed(token) == null, "Completed collection consumed only once");
        check(collector.count() == 0, "Collection cleared after completion");
        collector.begin(); collector.cancel(); check(collector.count() == 0, "Cancel discards samples");
        System.out.println("PASS " + checks + " synthetic core checks; no identity or liveness claim");
    }
}
