// SPDX-License-Identifier: Apache-2.0
import com.android.tools.smali.dexlib2.Opcode;
import com.android.tools.smali.dexlib2.Opcodes;
import com.android.tools.smali.dexlib2.dexbacked.DexBackedDexFile;
import com.android.tools.smali.dexlib2.iface.ClassDef;
import com.android.tools.smali.dexlib2.iface.Method;
import com.android.tools.smali.dexlib2.iface.instruction.Instruction;
import com.android.tools.smali.dexlib2.immutable.ImmutableClassDef;
import com.android.tools.smali.dexlib2.immutable.ImmutableDexFile;
import com.android.tools.smali.dexlib2.immutable.ImmutableMethod;
import com.android.tools.smali.dexlib2.immutable.ImmutableMethodImplementation;
import com.android.tools.smali.dexlib2.immutable.ImmutableMethodParameter;
import com.android.tools.smali.dexlib2.immutable.instruction.*;
import com.android.tools.smali.dexlib2.immutable.reference.ImmutableFieldReference;
import com.android.tools.smali.dexlib2.immutable.reference.ImmutableMethodReference;
import com.android.tools.smali.dexlib2.writer.io.MemoryDataStore;
import com.android.tools.smali.dexlib2.writer.pool.DexPool;
import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

/** Fail-closed APK output transform: two method bodies, two added helper classes. */
public final class ShengSystemUiPowerPatcher {
    private static final String REVEAL = "Lcom/android/systemui/statusbar/PowerButtonReveal;";
    private static final String WAKE = "Lcom/android/systemui/keyguard/WakefulnessLifecycle;";
    private static final String EFFECT = "Lcom/android/systemui/sheng/PowerButtonEffect;";
    private static final String GEOMETRY = "Lcom/android/systemui/sheng/PowerButtonGeometry;";
    private static final String SCRIM = "Lcom/android/systemui/statusbar/LightRevealScrim;";
    private static final String CONTEXT = "Landroid/content/Context;";
    private static final String POINT = "Landroid/graphics/Point;";
    private static int reveals, wakes;

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }

    private static ImmutableMethod replacement(Method method, int registers,
            List<? extends Instruction> instructions) {
        require(method.getImplementation() != null, "Missing method code: " + method);
        require((method.getAccessFlags() & 0x8) == 0, "Target unexpectedly became static");
        require(method.getImplementation().getTryBlocks().isEmpty(), "Unexpected try blocks");
        return new ImmutableMethod(method.getDefiningClass(), method.getName(),
                method.getParameters(), method.getReturnType(), method.getAccessFlags(),
                method.getAnnotations(), method.getHiddenApiRestrictions(),
                new ImmutableMethodImplementation(registers, instructions, null, null));
    }

    private static Method patch(Method method) {
        if (method.getDefiningClass().equals(REVEAL)
                && method.getName().equals("setRevealAmountOnScrim")) {
            require(method.getParameterTypes().equals(List.of("F", SCRIM))
                    && method.getReturnType().equals("V"), "Reveal signature changed");
            reveals++;
            // Four registers: v0 temporary; p0=this=v1, p1=amount=v2, p2=scrim=v3.
            return replacement(method, 4, List.of(
                    new ImmutableInstruction22c(Opcode.IGET, 0, 1,
                            new ImmutableFieldReference(REVEAL, "powerButtonY", "F")),
                    new ImmutableInstruction35c(Opcode.INVOKE_STATIC, 3, 2, 3, 0, 0, 0,
                            new ImmutableMethodReference(EFFECT, "apply", List.of("F", SCRIM, "F"), "V")),
                    new ImmutableInstruction10x(Opcode.RETURN_VOID)));
        }
        if (method.getDefiningClass().equals(WAKE)
                && method.getName().equals("getPowerButtonOrigin")) {
            require(method.getParameterTypes().isEmpty() && method.getReturnType().equals(POINT),
                    "Wake origin signature changed");
            wakes++;
            return replacement(method, 2, List.of(
                    new ImmutableInstruction22c(Opcode.IGET_OBJECT, 0, 1,
                            new ImmutableFieldReference(WAKE, "mContext", CONTEXT)),
                    new ImmutableInstruction35c(Opcode.INVOKE_STATIC, 1, 0, 0, 0, 0, 0,
                            new ImmutableMethodReference(EFFECT, "wakeOrigin", List.of(CONTEXT), POINT)),
                    new ImmutableInstruction11x(Opcode.MOVE_RESULT_OBJECT, 0),
                    new ImmutableInstruction11x(Opcode.RETURN_OBJECT, 0)));
        }
        return method;
    }

    private static byte[] patchDex(byte[] input, Set<String> allTypes) throws Exception {
        var dex = DexBackedDexFile.fromInputStream(null, new ByteArrayInputStream(input));
        var classes = new ArrayList<ClassDef>();
        boolean changed = false;
        for (ClassDef cls : dex.getClasses()) {
            require(allTypes.add(cls.getType()), "Duplicate class: " + cls.getType());
            if (!cls.getType().equals(REVEAL) && !cls.getType().equals(WAKE)) {
                classes.add(cls);
                continue;
            }
            var methods = new ArrayList<Method>();
            for (Method method : cls.getMethods()) {
                Method result = patch(method);
                changed |= result != method;
                methods.add(result);
            }
            classes.add(new ImmutableClassDef(cls.getType(), cls.getAccessFlags(),
                    cls.getSuperclass(), cls.getInterfaces(), cls.getSourceFile(),
                    cls.getAnnotations(), cls.getFields(), methods));
        }
        if (!changed) return input;
        // This pinned dexlib2 can emit invalid pooled parameter debug tables for
        // R8's shared debug programs. Drop optional debugger names/line tables in
        // the rewritten dex; retain all code, catches, annotations and signatures.
        var executableClasses = new ArrayList<ClassDef>();
        for (ClassDef cls : classes) {
            var methods = new ArrayList<Method>();
            for (Method method : cls.getMethods()) {
                var parameters = method.getParameters().stream().map(parameter ->
                        new ImmutableMethodParameter(parameter.getType(), parameter.getAnnotations(), null)).toList();
                var code = method.getImplementation();
                methods.add(new ImmutableMethod(method.getDefiningClass(), method.getName(), parameters,
                        method.getReturnType(), method.getAccessFlags(), method.getAnnotations(),
                        method.getHiddenApiRestrictions(), code == null ? null
                            : new ImmutableMethodImplementation(code.getRegisterCount(),
                                    code.getInstructions(), code.getTryBlocks(), null)));
            }
            executableClasses.add(new ImmutableClassDef(cls.getType(), cls.getAccessFlags(),
                    cls.getSuperclass(), cls.getInterfaces(), cls.getSourceFile(), cls.getAnnotations(),
                    cls.getFields(), methods));
        }
        var output = new MemoryDataStore();
        try {
            DexPool.writeTo(output, new ImmutableDexFile(dex.getOpcodes(), executableClasses));
            byte[] bytes = output.getData();
            var verify = DexBackedDexFile.fromInputStream(null, new ByteArrayInputStream(bytes));
            require(verify.getClasses().size() == dex.getClasses().size(), "Class count changed");
            return bytes;
        } finally {
            output.close();
        }
    }

    private static void put(ZipOutputStream out, String name, byte[] bytes, long time) throws Exception {
        var entry = new ZipEntry(name);
        entry.setTime(time);
        out.putNextEntry(entry);
        out.write(bytes);
        out.closeEntry();
    }

    public static void main(String[] args) throws Exception {
        require(args.length == 3, "Expected original APK, helper dex JAR, output APK");
        Path output = Path.of(args[2]);
        // Soong owns the generated output; never change either input.
        byte[] helper;
        try (var jar = new ZipFile(args[1])) {
            require(jar.getEntry("classes.dex") != null, "Helper must be a dex JAR");
            helper = jar.getInputStream(jar.getEntry("classes.dex")).readAllBytes();
            require(jar.getEntry("classes2.dex") == null, "Unexpected helper multidex");
        }
        var helperDex = DexBackedDexFile.fromInputStream(null, new ByteArrayInputStream(helper));
        var helperTypes = new HashSet<String>();
        for (ClassDef cls : helperDex.getClasses()) helperTypes.add(cls.getType());
        require(helperTypes.equals(Set.of(EFFECT, GEOMETRY)), "Unexpected helper classes");
        var types = new HashSet<String>();
        var dexIndexes = new HashSet<Integer>();
        int dexCount = 0;
        try (var apk = new ZipFile(args[0]); var out = new ZipOutputStream(Files.newOutputStream(output))) {
            var entries = apk.entries();
            while (entries.hasMoreElements()) {
                var entry = entries.nextElement();
                String name = entry.getName();
                // AndroidAppImport applies the platform signature after the transform.
                if (name.startsWith("META-INF/") && (name.endsWith(".SF")
                        || name.endsWith(".RSA") || name.endsWith(".DSA")
                        || name.equals("META-INF/MANIFEST.MF"))) continue;
                byte[] bytes = apk.getInputStream(entry).readAllBytes();
                if (name.matches("classes([2-9]|[1-9][0-9]+)?\\.dex")) {
                    int index = name.equals("classes.dex") ? 1
                            : Integer.parseInt(name.substring(7, name.length() - 4));
                    require(dexIndexes.add(index), "Duplicate dex index");
                    dexCount++;
                    bytes = patchDex(bytes, types);
                }
                put(out, name, bytes, entry.getTime());
            }
            require(reveals == 1 && wakes == 1, "Expected exactly one definition of each target method; "
                    + "reveal=" + reveals + " wake=" + wakes);
            require(!types.contains(EFFECT) && !types.contains(GEOMETRY), "Helper already present");
            require(dexCount > 0, "Missing dex files");
            for (int index = 1; index <= dexCount; index++) {
                require(dexIndexes.contains(index), "Noncontiguous multidex layout");
            }
            put(out, "classes" + (dexCount + 1) + ".dex", helper, 1230768000000L);
        }
        // Every non-DEX, non-signature payload is retained byte for byte.
        try (var before = new ZipFile(args[0]); var after = new ZipFile(args[2])) {
            var entries = before.entries();
            while (entries.hasMoreElements()) {
                var entry = entries.nextElement();
                String name = entry.getName();
                if (name.endsWith(".dex") || name.startsWith("META-INF/")) continue;
                require(after.getEntry(name) != null && Arrays.equals(
                        before.getInputStream(entry).readAllBytes(),
                        after.getInputStream(after.getEntry(name)).readAllBytes()),
                        "Resource or manifest changed: " + name);
            }
        }
        System.out.println("Patched two power-button methods; resources and manifest unchanged.");
    }
}
