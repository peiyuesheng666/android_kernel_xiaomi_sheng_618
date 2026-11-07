// SPDX-License-Identifier: Apache-2.0
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.os.SystemClock;
import java.io.File;
import java.io.FileInputStream;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Decode a pinned, clear Dolby Vision fixture into memory; never use a camera or Surface. */
public final class ShengVideoDecodeProbe {
    private static final int FRAME_LIMIT = 60;
    private static final long TIMEOUT_MS = 45000;

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }

    private static String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder();
        for (byte value : bytes) result.append(String.format("%02x", value & 255));
        return result.toString();
    }

    private static String fileSha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (FileInputStream stream = new FileInputStream(file)) {
            byte[] block = new byte[65536];
            int count;
            while ((count = stream.read(block)) != -1) digest.update(block, 0, count);
        }
        return hex(digest.digest());
    }

    private static List<Long> decode(File fixture, String codecName, int cycle) throws Exception {
        MediaExtractor extractor = new MediaExtractor();
        MediaCodec codec = null;
        boolean started = false;
        try {
            extractor.setDataSource(fixture.getAbsolutePath());
            MediaFormat format = null;
            for (int track = 0; track < extractor.getTrackCount(); track++) {
                MediaFormat candidate = extractor.getTrackFormat(track);
                if ("video/dolby-vision".equals(candidate.getString(MediaFormat.KEY_MIME))) {
                    require(format == null, "Fixture must have exactly one Dolby Vision track");
                    format = candidate;
                    extractor.selectTrack(track);
                }
            }
            require(format != null, "Fixture does not declare a Dolby Vision video track");
            require(!format.containsKey("crypto-mode"), "Encrypted fixtures are not supported");
            System.out.println("cycle=" + cycle + " input_format=" + format);
            codec = MediaCodec.createByCodecName(codecName);
            MediaCodecInfo info = codec.getCodecInfo();
            require(!info.isEncoder() && !info.isAlias(), "Expected the actual decoder");
            require(Arrays.asList(info.getSupportedTypes()).contains("video/dolby-vision"),
                    "Decoder does not advertise Dolby Vision");
            require(info.getCapabilitiesForType("video/dolby-vision").isFormatSupported(format),
                    "Fixture format is outside the advertised decoder capabilities");
            // No output Surface: decoded buffers remain in memory and are never displayed.
            codec.configure(format, null, null, 0);
            codec.start();
            started = true;
            long deadline = SystemClock.elapsedRealtime() + TIMEOUT_MS;
            boolean inputEos = false, outputEos = false;
            int queued = 0;
            long lastInputPts = 0, outputBytes = 0;
            List<Long> timestamps = new ArrayList<>();
            MessageDigest checksum = MessageDigest.getInstance("SHA-256");
            MediaCodec.BufferInfo outputInfo = new MediaCodec.BufferInfo();
            while (!outputEos) {
                require(SystemClock.elapsedRealtime() < deadline, "Decoder failed to drain before timeout");
                if (!inputEos) {
                    int inputIndex = codec.dequeueInputBuffer(10000);
                    if (inputIndex >= 0) {
                        ByteBuffer buffer = codec.getInputBuffer(inputIndex);
                        require(buffer != null, "No input buffer");
                        buffer.clear();
                        long sampleSize = extractor.getSampleSize();
                        if (queued == FRAME_LIMIT || sampleSize < 0) {
                            codec.queueInputBuffer(inputIndex, 0, 0, lastInputPts + 1,
                                    MediaCodec.BUFFER_FLAG_END_OF_STREAM);
                            inputEos = true;
                        } else {
                            require(sampleSize > 0 && sampleSize <= buffer.remaining(),
                                    "Invalid or oversized compressed access unit");
                            require((extractor.getSampleFlags() & MediaExtractor.SAMPLE_FLAG_ENCRYPTED) == 0,
                                    "Encrypted samples are not supported");
                            int bytes = extractor.readSampleData(buffer, 0);
                            require(bytes == sampleSize, "Truncated compressed access unit");
                            lastInputPts = extractor.getSampleTime();
                            require(lastInputPts >= 0, "Invalid input timestamp");
                            codec.queueInputBuffer(inputIndex, 0, bytes, lastInputPts, 0);
                            queued++;
                            extractor.advance();
                        }
                    }
                }
                int outputIndex = codec.dequeueOutputBuffer(outputInfo, 10000);
                if (outputIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    MediaFormat output = codec.getOutputFormat();
                    require(output.getInteger(MediaFormat.KEY_WIDTH) > 0
                            && output.getInteger(MediaFormat.KEY_HEIGHT) > 0,
                            "Invalid output dimensions");
                    System.out.println("cycle=" + cycle + " output_format=" + output);
                } else if (outputIndex >= 0) {
                    try {
                        if (outputInfo.size > 0
                                && (outputInfo.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0) {
                            ByteBuffer buffer = codec.getOutputBuffer(outputIndex);
                            require(buffer != null && outputInfo.offset >= 0
                                    && (long) outputInfo.offset + outputInfo.size <= buffer.capacity(),
                                    "No readable decoded frame or invalid output bounds");
                            buffer.clear();
                            buffer.position(outputInfo.offset);
                            buffer.limit(outputInfo.offset + Math.min(outputInfo.size, 4096));
                            checksum.update(buffer);
                            timestamps.add(outputInfo.presentationTimeUs);
                            outputBytes += outputInfo.size;
                        }
                        outputEos = (outputInfo.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0;
                    } finally {
                        codec.releaseOutputBuffer(outputIndex, false);
                    }
                } else {
                    require(outputIndex == MediaCodec.INFO_TRY_AGAIN_LATER
                            || outputIndex == MediaCodec.INFO_OUTPUT_BUFFERS_CHANGED,
                            "Unexpected output status: " + outputIndex);
                }
            }
            require(inputEos && queued >= 8, "Fixture has too few compressed frames");
            require(timestamps.size() == queued && outputBytes > 0,
                    "Missing decoded frames: queued=" + queued + " decoded=" + timestamps.size());
            System.out.println("cycle=" + cycle + " queued=" + queued + " decoded="
                    + timestamps.size() + " output_bytes=" + outputBytes
                    + " sampled_output_sha256=" + hex(checksum.digest()) + " eos=true");
            return timestamps;
        } finally {
            // Release even when stop fails, so a diagnostic failure does not retain a codec.
            try {
                if (codec != null) {
                    try {
                        if (started) codec.stop();
                    } finally {
                        codec.release();
                    }
                }
            } finally {
                extractor.release();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        require(args.length == 3,
                "Usage: ShengVideoDecodeProbe <fixture.mp4> <sha256> <c2.dolby.decoder.hevc|avc>");
        File file = new File(args[0]);
        require(file.isFile() && file.length() <= 128L * 1024 * 1024,
                "Expected a regular fixture file of at most 128 MiB");
        require(args[1].matches("[0-9a-f]{64}") && args[1].equals(fileSha256(file)),
                "Fixture hash mismatch");
        require("c2.dolby.decoder.hevc".equals(args[2]) || "c2.dolby.decoder.avc".equals(args[2]),
                "Only explicit, non-secure Dolby video decoders are supported");
        List<Long> first = decode(file, args[2], 0);
        require(first.equals(decode(file, args[2], 1)), "Decoded timestamps changed between sessions");
        System.out.println("decode_sessions=2 frames_per_session=" + first.size()
                + " offscreen_only=true camera_used=false drm_tested=false");
    }
}
