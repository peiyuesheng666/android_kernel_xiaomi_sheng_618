# sheng network location

This directory integrates the tablet's original MetokNLP network location
provider as an independent system_ext privileged application. It contains no
public-platform patches and requires no vendor-tree edits.

## Build modules

Add `ShengMetokNLP` and `ShengLocationOverlay` to the device product's
`PRODUCT_PACKAGES`. The application requires its own permission XML module.

| Module | Installed file |
| --- | --- |
| `ShengMetokNLP` | `system_ext/priv-app/ShengMetokNLP/ShengMetokNLP.apk` |
| `privapp-permissions-sheng-location` | `system_ext/etc/permissions/privapp-permissions-sheng-location.xml` |
| `ShengLocationOverlay` | `system_ext/overlay/ShengLocationOverlay.apk` |

The APK declares the existing `com.android.location.provider` shared Java
library. Its four ARM64 JNI libraries remain inside the signed APK, are stored
uncompressed and start at page-aligned offsets. Their dynamic dependencies are
only the public Android libraries listed in `PROVENANCE.json`; those libraries
are present in the current system's public-libraries list. No separately
installed Xiaomi native libraries are needed for these dependencies.

## Original APK and signing

The source is the read-only extracted
`product/priv-app/MetokNLP/MetokNLP.apk` from the user's
OS3.0.303.0.WNXCNXM firmware. It has package `com.xiaomi.metoknlp`, version
`16.2025.12.01` (16017), target SDK 33 and SHA256
`846c84ea6468d3e3e6e71496ec3ac0fb91760ced00427e7c062e5da01384e8d3`.

The application keeps its original Xiaomi v3 certificate. `presigned` and
`preprocessed` preserve the complete APK; it is not signed with the ROM's
platform key. This avoids automatically giving a proprietary provider unrelated
platform-signature privileges. The separate resource overlay is platform signed.

The stock `classes.dex` is compressed. This product enables
`UncompressPrivAppDex`; the APK therefore needs the documented
`skip_preprocessed_apk_checks` exception, while its JNI storage/alignment already
passes normal checks. Dex preoptimization is disabled for this import so no
modified APK or stock oat files are installed. If a future product disables
`UncompressPrivAppDex`, reassess the exception: Soong rejects an unnecessary
skip flag. The original signature must still remain intact.

The extractor is repeatable and refuses an unexpected APK or library hash:

```sh
python3 device/xiaomi/sheng/location/extract_metoknlp.py \
    --source-dump /root/sheng-lineage/firmware-dump/partitions
python3 device/xiaomi/sheng/location/extract_metoknlp.py --check
```

It reads firmware inputs and writes only this directory's proprietary APK. It
never extracts stock oat files or changes the APK manifest/signature.

## Permissions and provider selection

The privileged allowlist grants only `INSTALL_LOCATION_PROVIDER`,
`LOCAL_MAC_ADDRESS` and `LOCATION_HARDWARE`. The stock manifest also asks for
phone modification, user management, diagnostic and privileged phone-state
permissions; explicit deny entries prevent privileged-permission enforcement
errors without granting these privileges. Its signature-only
`INTERACT_ACROSS_USERS_FULL` request is not granted with the original Xiaomi
certificate. Runtime validation must confirm the provider tolerates these
denials on this Wi-Fi-only tablet before the integration is declared working.

`ShengLocationOverlay` adds MetokNLP only to
`config_locationExtraPackageNames`. Android's existing default permission
policy grants requested fine, coarse and background location permissions to
extra packages without `SYSTEM_FIXED`, so the user can revoke them. The r9
default-permissions XML also declares the three requested location grants with
`fixed=false`, retaining prior user decisions when the default policy runs.
On an existing user, adding a new system app does not itself rerun that policy;
the r8 first-install test applied those three grants once. This avoids fixed grants from
adding MetokNLP to `config_locationProviderPackageNames`.

The AOSP fused provider list and automatic network/geocoder service discovery
remain unchanged. The network service advertises the standard v2/v3 network
provider actions; installing it does not create GPS hardware support. Turning
location off or revoking its permissions must remain effective.

The overlay has no `targetName`. The current framework-res APK declares no
overlayable groups; idmap2 allows these resources to be overridden by a
preinstalled overlay. A separate platform-signed system_ext overlay keeps this
change independent of the existing ODM display overlay. Future upstream
overlayable changes must be checked again instead of assuming the current
policy remains valid.

## Bounded verification

`ShengNetworkLocationProbe.java` is source for the maintainer's root
`app_process` diagnostic. It checks that a real `network` provider exists and
is enabled, requests one current fix, and ends after at most 60 seconds. It
prints provider name, elapsed time, fix age, accuracy and mock status only. It
does not print coordinates, SSIDs, MAC addresses or location extras, install a
mock provider, or enable location settings. It must be run only as the
authorized verification step; adding the source does not request a location.

r8 was compiled, flashed and booted. The original geocoder constructor was
blocked by ART's non-SDK policy, repeatedly terminating the shared process.
Temporary isolation of that component and the three runtime grants yielded a
real network fix with age 9 ms, accuracy 45 m and mock=false. This does not mark
the unmodified r8 integration as successful. See the device's
`docs/network-location-r8-validation.json`.

r9 adds `system_ext/etc/sysconfig/sheng-location.xml` for the original system
provider package's non-SDK interface access. It changes neither the platform
source nor global hidden-API policy, preserves the Xiaomi signature, and adds no
unrelated runtime/privileged grants. The geocoder's Binder methods, transaction
order and request getter signatures match the current platform; actual calls
and reboot behavior still require validation. This provider serves all clients
using Android's standard network-location API; client apps need no package
allowlist. The temporary disabled geocoder component must be reset to its default
after installing the persisted repair.
