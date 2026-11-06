import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioTimestamp;
import android.media.AudioTrack;

/** Low-volume PCM playback only; no microphone, camera, files or effects. */
public final class ShengStereoProbe {
    private static final int RATE = 48000;

    private static void segment(AudioTrack track, String name, int seconds,
                                boolean left, boolean right) {
        System.out.println("BEGIN " + name);
        short[] samples = new short[960 * 2];
        long frame = 0;
        for (int chunk = 0; chunk < seconds * 50; ++chunk) {
            for (int i = 0; i < 960; ++i, ++frame) {
                // 500 Hz left, 800 Hz right, at -24 dBFS with short fades.
                double fade = Math.min(1.0, Math.min(frame / 2400.0,
                                  (seconds * RATE - frame) / 2400.0));
                samples[i * 2] = left ? (short)(2000 * fade * Math.sin(2 * Math.PI * 500 * frame / RATE)) : 0;
                samples[i * 2 + 1] = right ? (short)(2000 * fade * Math.sin(2 * Math.PI * 800 * frame / RATE)) : 0;
            }
            int offset = 0;
            while (offset < samples.length) {
                int written = track.write(samples, offset, samples.length - offset);
                if (written <= 0) throw new IllegalStateException("AudioTrack write " + written);
                offset += written;
            }
            if (chunk % 500 == 0) {
                AudioTimestamp timestamp = new AudioTimestamp();
                boolean valid = track.getTimestamp(timestamp);
                System.out.println("PROGRESS " + name + " seconds=" + chunk / 50 +
                        " underruns=" + track.getUnderrunCount() + " timestamp=" + valid +
                        " frames=" + timestamp.framePosition);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        int bytes = Math.max(AudioTrack.getMinBufferSize(RATE, AudioFormat.CHANNEL_OUT_STEREO,
                AudioFormat.ENCODING_PCM_16BIT) * 4, RATE * 4 / 5);
        AudioTrack track = new AudioTrack(AudioManager.STREAM_MUSIC, RATE,
                AudioFormat.CHANNEL_OUT_STEREO, AudioFormat.ENCODING_PCM_16BIT,
                bytes, AudioTrack.MODE_STREAM);
        if (track.getState() != AudioTrack.STATE_INITIALIZED)
            throw new IllegalStateException("AudioTrack not initialized");
        try {
            track.play();
            segment(track, "LEFT_500HZ", 5, true, false);
            segment(track, "SILENCE", 1, false, false);
            segment(track, "RIGHT_800HZ", 5, false, true);
            segment(track, "SILENCE", 1, false, false);
            segment(track, "LEFT_500HZ", 5, true, false);
            segment(track, "SILENCE", 1, false, false);
            segment(track, "RIGHT_800HZ", 5, false, true);
            segment(track, "BOTH_CONTINUOUS", 90, true, true);
            Thread.sleep(500);
            System.out.println("PASS completed 113s PCM; underruns=" + track.getUnderrunCount());
        } finally {
            track.stop();
            track.release();
        }
        // app_process starts Binder worker threads; terminate after the probe.
        System.exit(0);
    }
}
