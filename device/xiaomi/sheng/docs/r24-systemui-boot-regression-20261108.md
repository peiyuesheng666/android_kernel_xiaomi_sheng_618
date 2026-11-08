# r24 SystemUI boot regression and scoped rollback

The user reported reaching the second boot screen and then remaining at
“平板电脑正在启动”. Target ca10ede3 returned to ADB. Read-only checks confirmed
sheng, slot b, sys.boot_completed=1 and bootanim stopped. SystemUI repeatedly
crashed while instantiating CustomizationProvider, with NoSuchFieldError for
uriMatcher. The installed SystemUI APK hash matched the frozen r24 APK.

An independent raw DEX class_data read found seven instance fields in the
original CustomizationProvider, including uriMatcher, and zero in the transformed
classes2.dex. The pinned dexlib2 ChainedIterator returns itself from iterator().
Passing getFields() to the combined-fields ImmutableClassDef constructor causes
its static-field filter to consume that iterable before its instance-field
filter runs. The previous canonical verifier repeated the same constructor and
could therefore hide the loss. Its old success receipt is not runtime proof.

After announcing the adbd restart, adb root was executed only for ca10ede3.
rollback_sheng_r24.ps1 verifies all six installed r24 partition hashes and the
accepted r22 restoration images before entering fastbootd. It restores only
system_ext_b and vbmeta_system_b, keeping the r24 vendor repair, data and slot.
Both flash commands and the reboot command completed successfully. ADB returned,
the user confirmed reaching the lock screen/launcher and all six partition hashes
matched the restored chain. Original SystemUI PID 3539 remained stable during
automatic regression. No recovery or other connected tablet was operated.

Evidence is in workspace reports/device/r24-boot-stuck-20261108 and
reports/device/rollback-r24-20261108-071109. The source correction and stronger
field checks are being validated separately. r24 power-animation acceptance
is withdrawn. The sealed r25 images assume the failed r24 system_ext baseline;
do not bypass their baseline guard or flash that old SystemUI again. A new
reviewed image chain is needed before resuming that batch.

## Source correction and validation

The patcher now passes static/instance fields and direct/virtual methods through
separate constructor arguments. The verifier compares decoded static and instance
field declarations, access flags, values, annotations and restrictions before
canonical code comparison. The original broken r24 APK is rejected by this check.
The fixed candidate and signed output preserve all 37,424 original classes and
their fields, retain non-DEX payload bytes, and change only the intended two
method bodies with two helper classes. Six malformed-input cases also pass.

The host source was first compiled independently. Then an incremental module
build copied six exact existing Soong edges into a small Ninja graph: javac,
JAR merge, APK transform, JNI/dex uncompression and platform signing. Build flags
and real tool dependencies were preserved. The signed APK is
a38be61543b88e1510e447f1ddceea30b3bb24a5069f74df42d5a53943acdbd8;
its platform certificate and unsigned candidate payload comparison pass. The
old installed PRODUCT APK remains untouched; the corrected signed intermediate
and diagnostic copy are ready for a later reviewed install/package step.

The first subset attempt failed on a missing host-tool alias. The second found
conflicting dist/nodist helper definitions; restricting the scan to numbered
shards resolved that graph-selection error. The third completed all six edges.
These attempts are retained under hardware-diagnostics/systemui-field-formal-module-20261108*.
Fresh-fetch prebuild and postbuild physical audits passed for 20 public
repositories, with the same heads and all 1,243 repo projects clean. This is a
module build, not a completed full product build or a runtime pass. No fixed
APK has been flashed. The user then prohibited SystemUI changes and excluded
power-button animation from the bug list. The module and transform tools have
been removed; the correction described above is historical evidence only.
Exact evidence hashes are in systemui-field-fix-validation-20261108.json.
