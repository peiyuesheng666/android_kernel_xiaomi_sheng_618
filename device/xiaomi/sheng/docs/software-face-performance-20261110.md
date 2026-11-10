# Software face preview performance candidate 0.3

The user reported a clear but slow preview and requested faster face work on
2026-11-10. Version 0.2 throttled the entire software preview and inference
pipeline to one frame every 200 ms. Full-size RGBA Bitmap creation and drawing
shared the camera callback thread with YuNet and SFace inference.

Version 0.3 gives Camera2 a hardware TextureView output and a separate YUV
analysis output with matching aspect ratios. The session requests the best
supported AE range at or below 30 FPS. This is a requested rate, not a measured
30 FPS result. YUV resolution remains at most 1280x960, retaining the reviewed
model, feature and image-quality settings. Preview geometry undoes the default
TextureView stretch and applies fit-center rotation and display-only mirroring.

Camera callbacks drain and close the latest Image even while inference is busy.
Selected frames are copied using stride-aware bulk row reads, then their Image
is closed before inference starts on a separate HandlerThread. AnalysisGate
permits one inference at a time with a 100 ms minimum interval. Existing 250 ms
enrollment sampling avoids redundant SFace feature computation. Epoch, purpose
and collector generation checks reject results from stopped cameras and earlier
operations. Copied pixels and embedding arrays are cleared. Stopping preview or
destroying its surface cancels capture and covers the last texture with black.

Private model files are reused only after verifying their pinned SHA256 values;
APK recovery remains available for stale or corrupt files. Comparison guidance
and the similarity score now share one UI update, preventing the ordinary
guidance update from consuming the throttle before the score is displayed.

The engine-only benchmark generates blank NV21 matrices. It does not open a
camera or measure face accuracy. Pipeline logging records frame counts and
timings only. No camera images, facial templates or similarity values are
exported in these logs. User-operated camera trials remain required.

References were refreshed for this batch: piano seventeen
8c0bb4b9d15ea349eaa09d6de0aa4fec43f7ff41, nuwa lineage-24.0
8e2b6ca4375919035587115189760eed64f14b8d and sm8550-common
63da741c41384a23416159f148f7ef7c85c8ea61. The earlier face-specific review still
applies: no applicable sheng preview repair was imported. The source-owned app
keeps pinned OpenCV 4.13.0, YuNet and SFace dependencies and their license texts.
Original SystemUI and public ROM repositories were not modified.

## Build and installation evidence

- Scoped Java/D8 APK build: passed in approximately eight seconds; 52 core,
  10 embedding/collector and 110 pipeline checks passed (172 total).
- Signing, packaged dependencies/licenses and 16 KiB ZIP alignment: passed.
- Final APK SHA256:
  `2b6acc0376c3258906144fb2d9db9f4897733ce3602c93e4c3c3a3c5b0e9571f`.
- Installed on ca10ede3 as versionCode 3 / versionName 0.3. Device APK hash
  matches the final artifact. No partition flash or reboot was required.
- An initial candidate used a different development signing key and was rejected
  by PackageManager. The original signing key was recovered from the 0.2 build
  receipt, verified against the installed certificate and reused for `install
  -r`. No uninstall, application-data clear or key replacement was performed.
  Explicit `--signing-dir` now requires an existing key/password pair.
- Installed/final certificate SHA256:
  `4a14705d41b1e65921ca04e0b4eb6e23575b1be15ac3abe320ee68d187fdc527`.
- Final installed APK passed native engine/model self-test. Five timed warm
  synthetic 1280x960 iterations averaged detection 79.46 ms, total analysis
  88.85 ms and separate blank feature extraction 76.12 ms. The blank-frame
  total does not include real-face alignment, quality checks or embedding.
- No active camera clients were observed during self-test. Tablet log dates
  currently differ from host dates; the final process PID 5645 and installed
  APK hash identify the tested candidate. An earlier self-test after the
  rejected installation belonged to 0.2 and is not evidence for 0.3.

Final artifact: `artifacts/ShengFaceLab-performance-20261110-final/ShengFaceLab.apk`.
Session receipts: `reports/device/20261110-resume/face-performance/`, including
`build-review-final.json`, `build-final.log`, `signature-check.json`,
`runtime-final.txt`, `installed-final.txt` and `camera-state-final.txt`.

## Pending acceptance

Actual hardware preview/detection FPS, the two-output camera session, green-box
alignment and mirror/orientation behavior, stop/reopen, enrollment and
comparison require user-operated trials. No measured preview acceleration or
identity/liveness acceptance is claimed yet. Normal Soong/product integration
is still pending. This remains FaceLab; the formal Settings-only FaceUnlock UI,
biometric service registration and credential-authorized system unlock are
separate unfinished work.
