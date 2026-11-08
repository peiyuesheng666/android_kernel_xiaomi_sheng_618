# Protected face-preview composition investigation

The user's r38 enrollment attempts did not complete. At 08:46:28.740 and
08:55:27.211 UTC on 2026-11-08, SurfaceFlinger's RenderEngine aborted while
importing a protected 640x480 UBWC camera buffer (format 0x7fa30c06). Both
crashes immediately followed a sleep request. The kernel boot ID remained
unchanged across the framework restarts. The requested live-layer capture
arrived after the second failure and shows boot animation, not an active
enrollment preview; it cannot establish the preview's composition strategy.

`tools/ShengProtectedImportProbe.cpp` reproduces the import failure using
empty offscreen GraphicBuffers. It opens no camera, maps no CPU memory,
samples no textures, draws nothing and reads no pixels. Each protected test
uses a protected EGL context, pbuffer and EGLImage attribute. Ordinary RGBA,
protected RGBA and protected UBWC imports succeed; adding CAMERA_WRITE to
protected UBWC with texture/composer usage produces EGL_BAD_ACCESS (0x3002).
All four allocations succeed. The separate diagnostic process exits normally
and leaves SurfaceFlinger, system_server and SystemUI PIDs unchanged.

This narrows the import failure to the tested protected camera combination;
it does not establish that every camera format fails, that GPU sampling works
for the other cases, or that the enrollment stall has the same cause. The
diagnostic runs in the su domain; production-domain permissions remain a
separate question. The temporary executable was removed from the device.

Fresh pre/post audits passed for 22 public repositories, including Skia, and
all 1243 project statuses. The probe is a scoped diagnostic build, outside
product installation. Exact build and runtime receipts are
r38-protected-import-build-20261108.json and
r38-protected-import-runtime-20261108.json. Raw evidence remains outside Git
in reports/device/r38-face-runtime-20261108.

The pinned platform enables RenderEngine's protected context from
ro.surface_flinger.protected_contents. Output.cpp combines that capability
with the display's protected state. LayerFE.cpp substitutes an opaque black
layer, with the source buffer cleared, when protected content would otherwise
be composed into an unprotected target. A device configuration candidate can
use this existing fail-closed path while HWC continues to handle protected
buffers directly. It would affect all protected client composition, so
protected video, hardware preview and sleep/wake regressions are required.
Neither the candidate nor this investigation constitutes accepted enrollment
or authentication.

The user's piano reference was reviewed on 2026-11-08, including its optional
FaceUnlock patch, patch runner, manifests and vendor payload paths. The patch
changes the co.aospa.sense application's tablet orientation and preview aspect
ratio; it does not repair protected Xiaomi camera-buffer imports. That app is
absent from the current sheng LineageOS checkout. No implementation was copied
and no protected-composition property was changed. See
[piano-face-reference-review-20261108.md](piano-face-reference-review-20261108.md)
and its exact-source JSON receipt for the applicable ideas and limitations.
