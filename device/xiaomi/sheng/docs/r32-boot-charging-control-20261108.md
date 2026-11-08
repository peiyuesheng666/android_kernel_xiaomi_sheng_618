# r32 startup investigation

Target: ca10ede3, sheng, slot b. The official-system tablet was not operated.

r32 expanded vendor_b from 303517696 to 352321536 bytes and wrote the five
reviewed images. The user reported the second startup screen. At uptime three
minutes, system_server was repeatedly killed by Watchdog; SystemUI had not yet
started. The main thread waited in ChargingControlController's constructor for
vendor.lineage.health.IChargingControl/default. The existing health daemon was
running, but its constructor repeatedly failed access(R_OK | W_OK) against the
four default charging paths. Three paths do not exist; the actual class attribute
/sys/class/qcom-battery/input_suspend was root:root 0644. Its ueventd rule alone
had not applied the required permissions on this boot.

The public health constructor loops until a candidate is accessible and only
registers the Binder services afterwards. This explains the system_server
Watchdog loop. The face AIDL and Xiaomi HIDL daemons were already running and
registered; their startup was not the blocking stack. This evidence does not
establish why an older boot obtained usable charging permissions.

After announcing adb root, the agent corrected only the live charging attribute's
ownership/mode to system:system 0660. The first toybox chown invocation mistakenly
used init-style separate user/group arguments; it changed the owner but reported
an extra read-only operand. The following explicit 1000:1000 invocation completed
the group correction. No charging attribute value was written; input_suspend
remained 0. The existing daemon registered both IChargingControl and IFastCharge,
sys.boot_completed became 1, and SystemUI started. No reboot or image rollback
was needed for recovery. This is temporary recovery, not a persistent fix.

The r32 guarded VerifyRuntime check then verified all seven partition hashes,
fourteen payload files, nine new-node metadata entries, and original SystemUI.
Evidence: reports/device/r32-20261108-121958 and
reports/device/r32-boot-investigation-20261108. Subsequent system_server/SystemUI
PIDs remained 6631/6929 and the crash buffer was empty.

Face status: IFace/default and IMiFace/default registered in their intended
SELinux domains under Enforcing. Framework initialization enumerated zero faces;
the agent did not invoke camera capture, enrollment, or authentication. Full
user-facing face unlock is unverified.

Thermal status: report.dump, thermal.dump, last_thermal.dump became 1000:1000
with 0664, 0644, 0644 respectively without manual ownership changes. The fourth
thermal-global-mode file remained 0:1000 0664. Do not claim four-file ownership
acceptance or second-boot validation. The next boot must verify these results
again, alongside the persistent charging-node permission repair.

Full product/module builds remain uncompleted. All implementation changes remain
inside device/xiaomi/sheng; public sources and SystemUI remain unchanged.
