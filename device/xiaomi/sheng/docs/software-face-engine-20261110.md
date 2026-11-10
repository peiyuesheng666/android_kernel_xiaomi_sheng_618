# Source-owned software face engine candidate

The user resumed face enrollment/unlock work on 2026-11-10. The r38 protected
preview path remains unaccepted. Continue the ordinary Camera2 application
written in this tree, preserving original SystemUI.

Fresh references: piano seventeen at
8c0bb4b9d15ea349eaa09d6de0aa4fec43f7ff41 and nuwa lineage-24.0 at
8e2b6ca4375919035587115189760eed64f14b8d. Piano changed only BoardConfig from
the previous review; it still supplies no sheng protected-preview repair.
Nuwa's reviewed revision is unchanged. Their implementations were not imported.

The resumed 0.2 candidate uses pinned OpenCV 4.13.0, YuNet detection and SFace
128-dimensional output instead of vendor face rectangles and experimental LBP.
Ordinary preview can use up to 1280x960. It provides explicit guidance,
twelve-sample progress and a 30-second collection deadline. Generation tokens
cancel old callbacks. A separate encrypted template format binds model/version.
An engine-only check uses generated blank matrices without opening a camera.
Capture is an explicit user action. No image persistence, background camera,
network permission, biometric registration or unlock action was added.

The builder packages ARM64 OpenCV/C++ runtimes, both models, SDK licenses and
supplementary third-party/NDK notices. engine-dependencies.json pins dependency,
model and notice hashes, with separate model licenses. Original license texts
are preserved. This local development package does not certify the whole tree
for public redistribution. Normal Soong staging/system integration is pending.

Final APK: 61,891,032 bytes, SHA256
22c55502aa9085861b6cc35803efb718898749bb272626442fd67ecfaaf93006.
All 52 existing synthetic checks and ten embedding/collector checks passed;
Java/D8 compilation, signing, package contents and 16 KiB ZIP alignment passed.
Fresh pre/final-post audits passed for 21 known public repositories and 1243
project statuses, plus SDK/R8/JDK toolchain byte checks. APK and detailed build
receipt are in artifacts/ShengFaceLab-20261110. Sources were compiled directly
from this workspace via --source, with public build inputs read-only in WSL.

Android installation and engine runtime testing await successful r38 startup.
Enrollment, identity accuracy, liveness, credential validation and system unlock
remain unaccepted. No camera or personal image/template was acquired by the agent.
