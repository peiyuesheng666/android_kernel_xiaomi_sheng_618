// SPDX-License-Identifier: Apache-2.0
package org.lineageos.sheng.facelab;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.AtomicFile;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.security.KeyStore;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Encrypted, app-private, credential-encrypted storage. No frames or images are persisted. */
final class TemplateStore {
    private static final int MAGIC = 0x53464c32, VERSION = 2, MAX_BYTES = 64 * 1024;
    private static final String ALIAS = "sheng_face_lab_sface_v2";
    private static final byte[] AAD = ("ShengFaceLab:SFace128:v2:"
            + "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79").getBytes(
            java.nio.charset.StandardCharsets.US_ASCII);
    private final AtomicFile file;

    TemplateStore(Context context) {
        if (context.isDeviceProtectedStorage()) throw new IllegalArgumentException("CE only");
        file = new AtomicFile(new File(context.getNoBackupFilesDir(), "face-sface-v2.aesgcm"));
    }

    private SecretKey key(boolean create) throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (!store.containsAlias(ALIAS)) {
            if (!create) throw new IllegalStateException("Template key missing");
            KeyGenerator generator = KeyGenerator.getInstance("AES", "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256).setUnlockedDeviceRequired(true).build());
            generator.generateKey();
        }
        return (SecretKey) store.getKey(ALIAS, null);
    }

    synchronized void save(float[][] samples) throws Exception {
        if (samples.length != SampleCollector.REQUIRED) throw new IllegalArgumentException("Count");
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream data = new DataOutputStream(buffer)) {
            data.writeInt(VERSION); data.writeInt(samples.length);
            for (float[] sample : samples) {
                FaceEmbedding.validate(sample);
                for (float value : sample) data.writeFloat(value);
            }
        }
        byte[] plain = buffer.toByteArray();
        FileOutputStream output = null;
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key(true)); cipher.updateAAD(AAD);
            byte[] encrypted = cipher.doFinal(plain), iv = cipher.getIV();
            if (iv.length != 12) throw new IllegalStateException("Unexpected GCM nonce length");
            output = file.startWrite();
            DataOutputStream data = new DataOutputStream(output);
            data.writeInt(MAGIC); data.write(iv); data.write(encrypted); data.flush();
            file.finishWrite(output); output = null;
        } finally {
            if (output != null) file.failWrite(output);
            Arrays.fill(plain, (byte) 0);
        }
    }

    synchronized float[][] load() throws Exception {
        byte[] packed;
        try (FileInputStream input = file.openRead()) {
            long length = input.getChannel().size();
            if (length < 32 || length > MAX_BYTES) throw new IllegalStateException("Invalid file size");
            packed = new byte[(int) length];
            new DataInputStream(input).readFully(packed);
            if (input.read() != -1) throw new IllegalStateException("Template grew during read");
        } catch (FileNotFoundException absent) { return null; }
        if (packed.length < 32 || packed.length > MAX_BYTES)
            throw new IllegalStateException("Truncated template");
        byte[] plain = null;
        try (DataInputStream data = new DataInputStream(new ByteArrayInputStream(packed))) {
            if (data.readInt() != MAGIC) throw new IllegalStateException("Invalid template header");
            byte[] iv = new byte[12]; data.readFully(iv);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(false), new GCMParameterSpec(128, iv));
            byte[] ciphertext = new byte[packed.length - 16]; data.readFully(ciphertext);
            cipher.updateAAD(AAD); plain = cipher.doFinal(ciphertext);
            try (DataInputStream decoded = new DataInputStream(new ByteArrayInputStream(plain))) {
                if (decoded.readInt() != VERSION || decoded.readInt() != SampleCollector.REQUIRED)
                    throw new IllegalStateException("Invalid template version or count");
                float[][] samples = new float[SampleCollector.REQUIRED][FaceEmbedding.LENGTH];
                for (float[] sample : samples) {
                    for (int i = 0; i < sample.length; i++) sample[i] = decoded.readFloat();
                    FaceEmbedding.validate(sample);
                }
                if (decoded.available() != 0) throw new IllegalStateException("Trailing data");
                return samples;
            }
        } finally {
            Arrays.fill(packed, (byte) 0);
            if (plain != null) Arrays.fill(plain, (byte) 0);
        }
    }

    synchronized void delete() throws Exception {
        file.delete();
        KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        store.deleteEntry(ALIAS);
        if (file.getBaseFile().exists()) throw new IllegalStateException("Template deletion failed");
    }
}
