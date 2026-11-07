# Device-owned tablet compatibility

The user explicitly selected a device-tree compatibility layer after reviewing
the MIUI-detection tradeoff. Public source must remain manifest-pinned and
unchanged. Marketing name and numeric model must remain separate in Settings.

The unmodified installed Douyin 41.0.0 APK uses the tablet property plus
Class.forName("miui.os.Build") on the Xiaomi/Redmi branch. Android already
reports sw813dp / xlarge and ro.build.characteristics=tablet. Its additional
class-presence requirement explains why those Android values alone do not
satisfy that branch. APK identity: reports/device/r20-runtime/aweme-base.apk;
classes32.dex X.16r4.LIZ and classes56.dex ToolUtils.isMiui.

interfaces/compat/tablet supplies the small miui.os.Build compatibility class,
with IS_TABLET derived from the real Android property. It does not supply
MIUI services or a fake MIUI version property. Other applications can also
observe this class and may select vendor-specific paths; the class is not a
complete MIUI framework. Application regression checks remain necessary.

The board classpath adapter preserves the generated platform fragment byte
for byte and appends the jar to BOOTCLASSPATH and DEX2OATBOOTCLASSPATH. A
device-owned init definition keeps the standard derive_classpath executable,
user, groups and output, selecting the merged fragment through its supported
--bootclasspath-fragment argument. ART and other APEX fragments retain their
normal discovery and ordering. The public executable, platform boot-jar
configuration, package checks and hidden-API policy are unchanged. On-device
ART can regenerate artifacts for the expanded runtime classpath on first boot.

The jar is built as a normal system_ext Java library; the board-specific
runtime adapter does not modify the platform's shared framework jars.
All implementation, product integration and generation rules are below
device/xiaomi/sheng. The generated base fragment was compared byte-for-byte
with the installed r20 fragment (822 bytes). Android's official protobuf
converter decoded the merged result and verified that every original entry
was retained, followed by exactly the two intended additions. Duplicate
addition is rejected. Build and runtime acceptance are still pending.

The generated protobuf is staged under the module's generated/ directory.
BUILD_PREBUILT owns the separate built-module copy target; assigning both
rules the same output caused a Kati duplicate-command failure during the
first unified attempt. Only the device Android.mk was corrected.
