import android.media.AudioAttributes;
import android.media.MediaPlayer;
import android.media.MediaDataSource;
import java.io.RandomAccessFile;
import android.os.Handler;
import android.os.HandlerThread;
import java.util.concurrent.FutureTask;
import java.util.concurrent.atomic.AtomicBoolean;


/** Plays generated local codec samples only; no capture or recording. */
public final class ShengOffloadMediaProbe {
    private static final class FileSource extends MediaDataSource {
        private final RandomAccessFile input;
        FileSource(String path) throws Exception { input = new RandomAccessFile(path, "r"); }
        public synchronized int readAt(long position, byte[] data, int offset, int size)
                throws java.io.IOException {
            input.seek(position);
            return input.read(data, offset, size);
        }
        public long getSize() throws java.io.IOException { return input.length(); }
        public void close() throws java.io.IOException { input.close(); }
    }
    public static void main(String[] args) throws Exception {
        HandlerThread events = new HandlerThread("sheng-offload-probe-events");
        events.start();
        FutureTask<MediaPlayer> create = new FutureTask<>(() -> new MediaPlayer());
        new Handler(events.getLooper()).post(create);
        MediaPlayer player = create.get();
        AtomicBoolean completed = new AtomicBoolean(false);
        AtomicBoolean failed = new AtomicBoolean(false);
        player.setOnCompletionListener(p -> {
            System.out.println("COMPLETED position=" + p.getCurrentPosition());
            completed.set(true);
        });
        player.setOnErrorListener((p, what, extra) -> {
            System.err.println("MEDIA_ERROR what=" + what + " extra=" + extra);
            failed.set(true);
            completed.set(true);
            return true;
        });
        try {
            player.setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build());
            player.setDataSource(new FileSource(args[0]));
            player.prepare();
            System.out.println("PREPARED path=" + args[0] + " duration=" + player.getDuration());
            int repeats = args.length > 1 ? Integer.parseInt(args[1]) : 1;
            for (int cycle = 1; cycle <= repeats; cycle++) {
              completed.set(false);
              player.start();
              System.out.println("START cycle=" + cycle);
              long started = System.currentTimeMillis();
              int lastPosition = -1;
              boolean paused = false;
              while (!completed.get() && System.currentTimeMillis() - started < player.getDuration() + 15000) {
                Thread.sleep(1000);
                int position = player.getCurrentPosition();
                if (args.length > 2 && !paused && position > 10000) {
                    player.pause();
                    System.out.println("PAUSED position=" + player.getCurrentPosition());
                    Thread.sleep(2000);
                    player.start();
                    System.out.println("RESUMED position=" + player.getCurrentPosition());
                    paused = true;
                }
                if ((System.currentTimeMillis() - started) / 1000 % 10 == 0)
                    System.out.println("PROGRESS elapsed=" + (System.currentTimeMillis() - started) / 1000
                            + " position=" + position + " playing=" + player.isPlaying());
                lastPosition = position;
                if (position >= player.getDuration() - 100 && !player.isPlaying()) break;
              }
              System.out.println("DONE cycle=" + cycle + " lastPosition=" + lastPosition
                      + " duration=" + player.getDuration() + " completed=" + completed.get());
              if (failed.get()) throw new IllegalStateException("Playback error");
              if (!completed.get() && lastPosition < player.getDuration() - 500)
                  throw new IllegalStateException("Playback did not reach the end");
            }
        } finally {
            player.release();
            events.quitSafely();
        }
        System.exit(0);
    }
}
