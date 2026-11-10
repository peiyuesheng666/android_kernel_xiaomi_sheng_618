#!/usr/bin/env python3
"""Test selection translation against the stock DMS surround branches."""
from pathlib import Path
import os
import subprocess
import tempfile


def main():
    device = Path(__file__).resolve().parents[1]
    java = Path('/root/sheng-lineage/lineage-24.0/prebuilts/jdk/jdk21/linux-x86/bin')
    with tempfile.TemporaryDirectory(prefix='sheng-dolby-profile-test-') as directory:
        work = Path(directory)
        sources = {
            'android/os/SystemProperties.java': '''package android.os;
public final class SystemProperties {
    public static int surround;
    public static int getInt(String key, int fallback) {
        if (!key.equals("persist.vendor.audio.dolbysurround.enable")) throw new AssertionError(key);
        return surround;
    }
}''',
            'android/media/audiofx/AudioEffect.java': '''package android.media.audiofx;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
public final class AudioEffect {
    public static final int SUCCESS = 0;
    public int selected, opcode, argument;
    public int setParameter(int key, byte[] data) {
        if (key != 5) throw new AssertionError(key);
        ByteBuffer values = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN);
        opcode = values.getInt() >>> 24;
        values.getInt(); argument = values.getInt();
        if (opcode == 10) {
            selected = argument;
            if (android.os.SystemProperties.surround == 0 && selected > 3) selected -= 4;
            else if (android.os.SystemProperties.surround != 0 && selected < 4) selected += 4;
        }
        return SUCCESS;
    }
    public int getParameter(int key, byte[] data) {
        ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN).putInt(selected);
        return 4;
    }
}''',
            'org/lineageos/sheng/dolby/ProfileTest.java': '''package org.lineageos.sheng.dolby;
import android.media.audiofx.AudioEffect;
import android.os.SystemProperties;
public final class ProfileTest {
    static void equal(int expected, int actual) {
        if (expected != actual) throw new AssertionError(expected + " != " + actual);
    }
    public static void main(String[] args) {
        AudioEffect effect = new AudioEffect();
        SystemProperties.surround = 0;
        for (int profile = 0; profile <= 8; profile++) {
            StockDms.setProfile(effect, profile);
            equal(profile, StockDms.getProfile(effect));
            equal(profile > 3 ? profile + 4 : profile, effect.argument);
        }
        for (int surround : new int[]{1, 2, -1}) {
            SystemProperties.surround = surround;
            StockDms.setProfile(effect, 8);
            equal(8, effect.argument); equal(8, StockDms.getProfile(effect));
        }
        for (int surround : new int[]{0, 1}) {
            SystemProperties.surround = surround;
            StockDms.setParameter(effect, 8, StockDms.DIALOG_AMOUNT, 9);
            equal(1, effect.opcode); equal(8, effect.argument);
            StockDms.resetProfile(effect, 8);
            equal(12, effect.opcode); equal(8, effect.argument);
        }
        for (int invalid : new int[]{-1, 9, 12, Integer.MAX_VALUE}) {
            try { StockDms.setProfile(effect, invalid); throw new AssertionError("Accepted " + invalid); }
            catch (IllegalArgumentException expected) { }
        }
        System.out.println("PASS: stock profile translation, Voice with surround off/on, direct parameter/reset IDs, invalid IDs");
    }
}''',
        }
        inputs = []
        for name, source in sources.items():
            path = work/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
            inputs.append(path)
        inputs.append(device/'dolby/ShengDolby/src/org/lineageos/sheng/dolby/StockDms.java')
        env = dict(os.environ, LANG='C.UTF-8', LC_ALL='C.UTF-8')
        subprocess.run(list(map(str, [java/'javac', '-encoding', 'UTF-8', '-d', work, *inputs])), env=env, check=True)
        subprocess.run([str(java/'java'), '-cp', str(work), 'org.lineageos.sheng.dolby.ProfileTest'], env=env, check=True)


if __name__ == '__main__':
    main()
