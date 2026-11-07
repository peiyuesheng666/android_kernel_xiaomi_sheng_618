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
Both flash commands and the reboot command completed successfully. ADB has
not yet returned after this rollback, so restored boot and partition readback
are still pending. No recovery or other connected tablet was operated.

Evidence is in workspace reports/device/r24-boot-stuck-20261108 and
reports/device/rollback-r24-20261108-071109. The source correction and stronger
field checks are being validated separately. r24 power-animation acceptance
is withdrawn. The sealed r25 images assume the failed r24 system_ext baseline;
do not bypass their baseline guard or flash that old SystemUI again. A new
reviewed image chain is needed before resuming that batch.
