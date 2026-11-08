# Source-owned software face enrollment investigation

The user requested a software replacement, using piano and nuwa as design
references while writing the application and integration in this tree.
The pinned reference reviews remain piano-face-reference-review-20261108.md
and nuwa-face-reference-review-20261108.md. The piano patch concerns tablet
preview geometry; neither reference provides a drop-in stock face repair.
ParanoidSense/DerpFest's app uses a custom ROM Binder interface and private
recognition libraries. No app, private library, model or source was imported
from those implementations.

## First capture prototype

`interfaces/biometrics/softwareface` contains the independently authored
ShengFaceLab development application. Its module is not in PRODUCT_PACKAGES.
It requests only CAMERA permission and opens it only after a user button
press. There is no background service, network permission, biometric sensor
registration, unlock action or SystemUI change. This is not a replacement
face HAL and is not an accepted face fix.

The initial pipeline requests ordinary YUV_420_888 frames from the front
Camera2 device. It pairs image and result timestamps with bounded pending
storage, maps sensor rectangles to the actual stream crop, and rotates and
mirrors only as appropriate for analysis versus display. Leaving the activity
or changing orientation cancels the collection and closes the camera. The
application does not use Xiaomi's secure preview buffers.

A capture requires system credential confirmation and collects 12 samples.
Only experimental spatial LBP histograms are persisted, encrypted with
AndroidKeyStore AES-GCM in app-private credential-encrypted no-backup storage.
Images and normalized face crops are not written to storage. Comparison shows
a numeric experimental distance; it has no acceptance threshold, liveness
claim or authentication-success path. This experimental descriptor is not
suitable for device unlock and is being superseded by a reviewed engine.

The scoped builder is `tools/build_sheng_face_lab.py`. It uses the pinned
Android 37 public SDK, JDK, aapt2, D8 and apksigner without regenerating the
ROM build graph. The scope is not a normal Soong/full-ROM build. It records
source/tool/APK hashes and verifies APK signatures and archive contents.
Apache-2.0 is stated for our source, with a complete module license text.

52 synthetic host checks passed: non-contiguous camera planes and offsets,
all four pixel rotations, sensor-to-stream crop mapping, clipped/invalid
input rejection, quality rejection, descriptor bounds and cancellation or
reuse of old collection tokens. These tests do not establish identity
accuracy, presentation-attack resistance or Android lifecycle correctness.

Fresh pre/post byte audits passed for 21 previously edited public projects
and all 1243 repo-managed project statuses. Three additional freshly fetched
toolchain repositories were byte-audited: prebuilts/sdk (26135 files),
prebuilts/r8 (34 files), prebuilts/jdk/jdk21 (1293 files).
Raw audit/build inputs stay under
`/root/sheng-lineage/hardware-diagnostics/sheng-software-face`.

## First device trial: failed enrollment

The first APK (version 0.1, 33171 bytes, SHA256
`b40f797457f55843a00e0bd8719ebfd30228a5a4bbaca3e6c123e36db33fa95a`)
was installed as an ordinary development app on ca10ede3/sheng/b. Launch
took 279 ms. Before user interaction, camera permission remained ungranted
and all camera clients were closed. No partition was written or ROM package
flashed. r38 and its existing stock face registration remained installed.

The user manually opened the camera and reported: a preview is visible,
enrollment shows neither success nor failure, and the preview is very blurry.
This is a failed trial, not an enrollment acceptance. The app's own log shows
`CameraMetadataJV: Expect face scores and rectangles to be non-null`.
The captured client configuration confirms an ordinary 640x480 YUV stream;
the UI additionally downsampled it to 320 pixels wide, explaining a concrete
loss of preview detail on this tablet. Metadata non-null failures are evidence
against depending on the vendor face rectangles as the only detector; they
do not establish why every enrollment attempt stalled.

The kernel boot ID remained f526546c-dd24-4dde-9d91-d6a50dd02cd6;
SurfaceFlinger/system_server/SystemUI remained 9026/9111/9431 in the subsequent
read-only check. This observation does not establish long-term stability.
No screenshots or camera images were collected by the agent. Raw textual
evidence is in reports/device/sheng-face-lab-20261108 and stays outside Git.

The next candidate must use a full-resolution ordinary preview, supply
explicit collection state and timeout feedback, and replace vendor-dependent
face localization and the experimental descriptor with a license-reviewed
open-source engine. The user authorized that dependency while retaining our
own app and system integration. License obligations apply to code, weights
and all bundled native dependencies; see OPEN_SOURCE_RELEASE_POLICY.md.

System integration, credential-token verification, user isolation, persistent
lockout and presentation-attack/identity testing remain unimplemented or
unvalidated. No app result is forwarded to the lockscreen or Keystore.
