// SPDX-License-Identifier: Apache-2.0
import com.android.tools.smali.dexlib2.Opcodes;
import com.android.tools.smali.dexlib2.Opcode;
import com.android.tools.smali.dexlib2.dexbacked.DexBackedDexFile;
import com.android.tools.smali.dexlib2.iface.ClassDef;
import com.android.tools.smali.dexlib2.iface.Method;
import com.android.tools.smali.dexlib2.iface.Field;
import com.android.tools.smali.dexlib2.util.MethodUtil;
import com.android.tools.smali.dexlib2.iface.instruction.Instruction;
import com.android.tools.smali.dexlib2.iface.instruction.ReferenceInstruction;
import com.android.tools.smali.dexlib2.iface.instruction.TwoRegisterInstruction;
import com.android.tools.smali.dexlib2.iface.instruction.FiveRegisterInstruction;
import com.android.tools.smali.dexlib2.iface.reference.FieldReference;
import com.android.tools.smali.dexlib2.iface.reference.MethodReference;
import com.android.tools.smali.dexlib2.builder.MutableMethodImplementation;
import com.android.tools.smali.dexlib2.builder.instruction.BuilderInstruction21c;
import com.android.tools.smali.dexlib2.immutable.*;
import com.android.tools.smali.dexlib2.writer.io.MemoryDataStore;
import com.android.tools.smali.dexlib2.writer.pool.DexPool;
import java.io.ByteArrayInputStream;
import java.util.*;
import java.util.zip.ZipFile;

/** Independent output review: retain every class member except two method bodies. */
public final class ShengSystemUiApkVerifier {
    private static final String REVEAL = "Lcom/android/systemui/statusbar/PowerButtonReveal;";
    private static final String WAKE = "Lcom/android/systemui/keyguard/WakefulnessLifecycle;";
    private static final String PREFIX = "Lcom/android/systemui/sheng/";
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }
    private static boolean target(Method method) {
        return (method.getDefiningClass().equals(REVEAL)
                    && method.getName().equals("setRevealAmountOnScrim"))
                || (method.getDefiningClass().equals(WAKE)
                    && method.getName().equals("getPowerButtonOrigin"));
    }
    private static Map<String, ClassDef> classes(ZipFile zip) throws Exception {
        Map<String, ClassDef> result = new TreeMap<>();
        int count = 0;
        for (var entry : Collections.list(zip.entries())) {
            if (!entry.getName().matches("classes([2-9]|[1-9][0-9]+)?\\.dex")) continue;
            count++;
            var dex = DexBackedDexFile.fromInputStream(null,
                    new ByteArrayInputStream(zip.getInputStream(entry).readAllBytes()));
            for (ClassDef cls : dex.getClasses()) {
                check(result.put(cls.getType(), cls) == null, "Duplicate type " + cls.getType());
                for (Method method : cls.getMethods()) {
                    for (var parameter : method.getParameters()) parameter.getName();
                    if (method.getImplementation() != null) {
                        for (var debug : method.getImplementation().getDebugItems()) debug.getCodeAddress();
                    }
                }
            }
        }
        for (int i = 1; i <= count; i++) {
            check(zip.getEntry(i == 1 ? "classes.dex" : "classes" + i + ".dex") != null,
                    "Missing dex index " + i);
        }
        return result;
    }
    private static byte[] canonical(ClassDef cls) throws Exception {
        List<Method> methods = new ArrayList<>();
        for (Method method : cls.getMethods()) {
            var original = method.getImplementation();
            var code = original == null ? null : new MutableMethodImplementation(
                    new ImmutableMethodImplementation(original.getRegisterCount(),
                            original.getInstructions(), original.getTryBlocks(), null));
            if (code != null && !target(method)) {
                // Pool reordering can promote const-string to jumbo. Normalize it with
                // builder-managed branch/debug/payload relocation before comparing code.
                for (int i = 0; i < code.getInstructions().size(); i++) {
                    var instruction = code.getInstructions().get(i);
                    if (instruction.getOpcode() == Opcode.CONST_STRING_JUMBO) {
                        var register = (com.android.tools.smali.dexlib2.iface.instruction.OneRegisterInstruction) instruction;
                        var reference = (ReferenceInstruction) instruction;
                        code.replaceInstruction(i, new BuilderInstruction21c(Opcode.CONST_STRING,
                                register.getRegisterA(), reference.getReference()));
                    }
                }
            }
            var parameters = method.getParameters().stream().map(parameter ->
                    new ImmutableMethodParameter(parameter.getType(), parameter.getAnnotations(), null)).toList();
            // DEX pooling can re-encode implicit parameter debug locals. Compare executable
            // behavior and annotations independently of optional debugger name/line tables.
            var implementation = code == null || target(method) ? null
                    : new ImmutableMethodImplementation(code.getRegisterCount(),
                            code.getInstructions(), code.getTryBlocks(), null);
            methods.add(new ImmutableMethod(method.getDefiningClass(),
                    method.getName(), parameters, method.getReturnType(),
                    method.getAccessFlags(), method.getAnnotations(),
                    method.getHiddenApiRestrictions(), implementation));
        }
        var copy = new ImmutableClassDef(cls.getType(), cls.getAccessFlags(), cls.getSuperclass(),
                cls.getInterfaces(), cls.getSourceFile(), cls.getAnnotations(),
                cls.getStaticFields(), cls.getInstanceFields(),
                methods.stream().filter(MethodUtil::isDirect).toList(),
                methods.stream().filter(method -> !MethodUtil.isDirect(method)).toList());
        var store = new MemoryDataStore();
        try {
            DexPool.writeTo(store, new ImmutableDexFile(Opcodes.forDexVersion(39), List.of(copy)));
            return store.getData();
        } finally {
            store.close();
        }
    }
    private static Map<String, List<Object>> fieldMembers(Iterable<? extends Field> fields) {
        Map<String, List<Object>> result = new TreeMap<>();
        for (Field field : fields) {
            check(result.put(field.toString(), Arrays.asList(field.getAccessFlags(),
                    field.getInitialValue(), field.getAnnotations(), field.getHiddenApiRestrictions())) == null,
                    "Duplicate field " + field);
        }
        return result;
    }
    private static void verifyFields(ClassDef before, ClassDef after) {
        // Compare decoded declarations directly. Re-pooling both sides with the
        // same constructor can hide a field-loss bug in that constructor.
        check(fieldMembers(before.getStaticFields()).equals(fieldMembers(after.getStaticFields())),
                "Static field declarations changed " + before.getType());
        check(fieldMembers(before.getInstanceFields()).equals(fieldMembers(after.getInstanceFields())),
                "Instance field declarations changed " + before.getType());
    }
    private static void verifyBody(Method method) {
        List<Instruction> code = new ArrayList<>();
        method.getImplementation().getInstructions().forEach(code::add);
        boolean reveal = method.getDefiningClass().equals(REVEAL);
        List<Opcode> expected = reveal
                ? List.of(Opcode.IGET, Opcode.INVOKE_STATIC, Opcode.RETURN_VOID)
                : List.of(Opcode.IGET_OBJECT, Opcode.INVOKE_STATIC,
                        Opcode.MOVE_RESULT_OBJECT, Opcode.RETURN_OBJECT);
        check(code.stream().map(Instruction::getOpcode).toList().equals(expected),
                "Unexpected target instructions " + method);
        String invoke = ((ReferenceInstruction) code.get(1)).getReference().toString();
        String field = ((ReferenceInstruction) code.get(0)).getReference().toString();
        check(field.equals(reveal ? REVEAL + "->powerButtonY:F" : WAKE + "->mContext:Landroid/content/Context;"),
                "Unexpected field " + field);
        var load = (TwoRegisterInstruction) code.get(0);
        check(load.getRegisterA() == 0 && load.getRegisterB() == 1, "Wrong field registers");
        var call = (FiveRegisterInstruction) code.get(1);
        check(call.getRegisterCount() == (reveal ? 3 : 1)
                && call.getRegisterC() == (reveal ? 2 : 0)
                && (!reveal || (call.getRegisterD() == 3 && call.getRegisterE() == 0)),
                "Wrong helper argument registers");
        check(invoke.equals(reveal
                ? PREFIX + "PowerButtonEffect;->apply(FLcom/android/systemui/statusbar/LightRevealScrim;F)V"
                : PREFIX + "PowerButtonEffect;->wakeOrigin(Landroid/content/Context;)Landroid/graphics/Point;"),
                "Unexpected helper invocation " + invoke);
        check(method.getImplementation().getRegisterCount() == (reveal ? 4 : 2),
                "Wrong register count");
    }
    private static boolean resolves(Map<String, ClassDef> classes, String owner, String name,
            Object reference, Set<String> visited) {
        if (!visited.add(owner)) return false;
        ClassDef cls = classes.get(owner);
        if (cls == null) {
            check(!owner.startsWith("Lcom/android/"), "Missing application class " + owner);
            return true; // Framework/boot-class-path members are checked by normal Java compilation.
        }
        if (reference instanceof MethodReference wanted) {
            for (Method method : cls.getMethods()) {
                if (method.getName().equals(name) && method.getParameterTypes().equals(wanted.getParameterTypes())
                        && method.getReturnType().equals(wanted.getReturnType())) return true;
            }
        } else if (reference instanceof FieldReference wanted) {
            for (var field : cls.getFields()) {
                if (field.getName().equals(name) && field.getType().equals(wanted.getType())) return true;
            }
        }
        // Static fields and private app methods cannot resolve through java.lang.Object.
        if (cls.getSuperclass() != null && !cls.getSuperclass().equals("Ljava/lang/Object;")
                && resolves(classes, cls.getSuperclass(), name, reference, visited)) return true;
        for (String parent : cls.getInterfaces()) {
            if (resolves(classes, parent, name, reference, visited)) return true;
        }
        return false;
    }
    private static void verifyHelperLinks(Map<String, ClassDef> classes, Set<String> helpers) {
        for (String type : helpers) {
            for (Method method : classes.get(type).getMethods()) {
                if (method.getImplementation() == null) continue;
                for (Instruction instruction : method.getImplementation().getInstructions()) {
                    if (!(instruction instanceof ReferenceInstruction ref)) continue;
                    var reference = ref.getReference();
                    if (reference instanceof MethodReference member) {
                        check(resolves(classes, member.getDefiningClass(), member.getName(), member, new HashSet<>()),
                                "Helper method was removed or renamed by R8: " + member);
                    } else if (reference instanceof FieldReference member) {
                        check(resolves(classes, member.getDefiningClass(), member.getName(), member, new HashSet<>()),
                                "Helper field was removed or renamed by R8: " + member);
                    }
                }
            }
        }
    }
    public static void main(String[] args) throws Exception {
        check(args.length == 2, "Expected original and signed transformed APK");
        try (var before = new ZipFile(args[0]); var after = new ZipFile(args[1])) {
            Set<String> payload = new TreeSet<>();
            for (var entry : Collections.list(before.entries())) {
                String name = entry.getName();
                if (name.endsWith(".dex") || name.startsWith("META-INF/")) continue;
                payload.add(name);
                check(after.getEntry(name) != null && Arrays.equals(
                        before.getInputStream(entry).readAllBytes(),
                        after.getInputStream(after.getEntry(name)).readAllBytes()),
                        "Payload changed " + name);
            }
            Set<String> afterPayload = new TreeSet<>();
            for (var entry : Collections.list(after.entries())) {
                String name = entry.getName();
                if (!name.endsWith(".dex") && !name.startsWith("META-INF/")) afterPayload.add(name);
            }
            check(payload.equals(afterPayload), "Non-DEX payload set changed");
            var oldClasses = classes(before);
            var newClasses = classes(after);
            Set<String> added = new TreeSet<>(newClasses.keySet());
            added.removeAll(oldClasses.keySet());
            check(added.equals(Set.of(PREFIX + "PowerButtonEffect;", PREFIX + "PowerButtonGeometry;")),
                    "Unexpected added classes " + added);
            check(newClasses.size() == oldClasses.size() + 2, "Class removal");
            verifyHelperLinks(newClasses, added);
            int targets = 0;
            for (var entry : oldClasses.entrySet()) {
                ClassDef next = newClasses.get(entry.getKey());
                check(next != null, "Missing class " + entry.getKey());
                verifyFields(entry.getValue(), next);
                check(next != null && Arrays.equals(canonical(entry.getValue()), canonical(next)),
                        "Unexpected class or member change " + entry.getKey());
                for (Method method : next.getMethods()) {
                    if (target(method)) { verifyBody(method); targets++; }
                }
            }
            check(targets == 2, "Wrong target count " + targets);
            System.out.println("Verified " + oldClasses.size()
                    + " original classes; only two method bodies changed; two helpers added; payload identical.");
        }
    }
}
