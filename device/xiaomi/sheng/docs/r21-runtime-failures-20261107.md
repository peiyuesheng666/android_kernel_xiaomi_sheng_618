# r21 runtime findings and r22 acceptance requirements

r21 booted, and all six installed partition hashes match the sealed r21 inputs.
The user reports that applications still fail to recognize the tablet and About
device crashes. Neither change is accepted. Panel physical DPI is corrected:
the ordinary-UID probe reads xdpi=294.145, ydpi=294.257, sw813dp and xlarge.
Build.MODEL remains 24018RPACC and the marketname property is unchanged.

## Settings controller failure

The retained crash is a NullPointerException at MyDeviceInfoFragment.onAttach:
use(DeviceNamePreferenceController.class) returns null before setHost. The RRO
was enabled, but both its local resources and referenced Settings resources
used build-time package ID 0x7f. Android's overlay dynamic reference table
remaps unmatched 0x7f references as overlay-local, including the controller
attribute. Linking the device RRO with --shared-lib assigns its local resources
dynamic package ID 0x00 and retains external Settings attributes at 0x7f.
AAPT2 confirms both classes of references remain distinct. A static installed
overlay cannot be upgraded from /data; the two diagnostic install attempts
were rejected, so they did not validate the live page. Rebooted UI/controller
checks are still required.

## Tablet classpath failure

The installed compatibility JAR matches the sealed build. The generated file
and zygote environment contain it, but the ordinary application UID receives
ClassNotFoundException for miui.os.Build. The platform-fragment adapter places
it before non-ART APEX jars, while the existing boot images describe the
original order. The retained ART log also reports a boot-classpath mismatch.

An isolated app_process experiment reproduced ClassNotFoundException with the
r21 order. Moving the JAR after all original BOOTCLASSPATH entries while
restoring the original DEX2OATBOOTCLASSPATH loaded the class and read
IS_TABLET=true. A diagnostic attempt that retained r21's amended DEX2OAT list
aborted only that isolated process with the explicit prefix-invariant error;
it did not restart zygote. The production adapter must append only the runtime
list, preserve the original DEX2OAT input list, retain the valid platform file
if its own transformation fails, and use the existing derive_classpath domain.
This experiment does not replace a normal app UID or Douyin acceptance check.

## Default name after a data reset

The user additionally requires the factory default editable device name to be
Xiaomi Pad 6S Pro 12.4. The pinned SettingsProvider DatabaseHelper initializes
Global.DEVICE_NAME from def_device_name_simple with Build.MODEL as its format
argument; its legacy migration uses def_device_name. Device-owned inline RRO
mappings for both strings avoid locale-specific target formats taking priority.
The current global name already has the marketing name; that existing value
alone cannot verify the factory default. Verify formatted provider resources
across installed locales without erasing data or overwriting custom names.

## Evidence and next acceptance

Raw evidence is in workspace reports/device/r21-runtime: crash-initial.txt,
installed-partition-hashes.txt, tablet-probe-expanded.txt, classpath-root.txt,
zygote-environ.txt, zygote-maps.txt, logcat-full.txt, isolated-fragment-order.txt,
isolated-append-with-original-dex2oat.txt and crash-after-isolated.txt.
The host resource probe is under /root/sheng-lineage/douyin-review-r22.

After the unified r22 build and flash: verify partition hashes, init/ART
startup, exact original classpath prefix, the normal-UID compatibility probe,
About-device and model-detail pages, all-locale default-name formatting and
the user's actual Douyin behavior. Do not count implementation or compilation
as two accepted fixes. AON remains unresolved; USB investigation stays paused.
Only the device tree changes. Public source is freshly checked at manifest
revisions, including ART. Announce every adb root before executing it; the one
used for this readback was announced and restarted only adbd.
