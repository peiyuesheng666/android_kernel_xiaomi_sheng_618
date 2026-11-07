// SPDX-License-Identifier: Apache-2.0
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaCodecList;
import java.util.Arrays;

/** Enumerate and allocate Dolby components without configuring or feeding media. */
public final class ShengCodec2Probe {
    public static void main(String[] args) throws Exception {
        int found = 0, allocated = 0;
        for (MediaCodecInfo info : new MediaCodecList(MediaCodecList.ALL_CODECS).getCodecInfos()) {
            String name = info.getName();
            if (!name.startsWith("c2.dolby.") || info.isAlias()) continue;
            found++;
            System.out.println("codec=" + name + " types=" + Arrays.toString(info.getSupportedTypes()));
            if (name.endsWith(".secure")) continue;
            MediaCodec codec = MediaCodec.createByCodecName(name);
            try {
                System.out.println("allocated=" + codec.getName());
                allocated++;
            } finally {
                codec.release();
            }
        }
        System.out.println("dolby_components=" + found + " allocated=" + allocated);
        if (found == 0 || allocated == 0) throw new IllegalStateException("No usable Dolby components");
    }
}
