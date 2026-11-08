# Missing original camera-format utility

The r31 offscreen Dolby Vision profile 8.1 reproduction fails to allocate format
275 (NV21_ZSL). The installed gralloc CameraInfo loads
libcamxexternalformatutils.so and resolves CamxFormatUtil_GetStrideInBytes and
the other layout functions. Both /vendor/lib64 and /odm/lib64 lack this library;
the allocation service repeatedly reports the unresolved stride function.
Evidence: reports/device/r31-video-investigation-20261108-101538.

The original sheng firmware contains vendor/lib64/libcamxexternalformatutils.so,
36264 bytes, SHA-256
7a1affdcba4a1dc835e5ac1944bbea864056fb38bec45c87538ef4df9a2be599.
It exports all sixteen symbols requested by the existing gralloc loader. Its
eight DT_NEEDED libraries are ordinary existing vendor/runtime dependencies.
The extraction list omitted this library while retaining the separate
odm/lib64/libcamximageformatutils.so, which does not replace this loader target.

Keep the original library unchanged in the device tree and install it with an
ordinary vendor cc_prebuilt_library_shared module. Retain ELF checks and all
original dependencies. The existing Qualcomm file-context rule labels this exact
library same_process_hal_file; preserve that label with root:root and mode 0644.
No new SELinux rule is needed. No gralloc source, pixel-format reinterpretation, camera
HAL, Dolby library or SystemUI modification is required for this missing file.

The reproduction's diagnostic Java process timed out and exited; the monitored
system and Dolby service PIDs stayed stable. Its crash-buffer exception is a
diagnostic failure, not a newly established native service crash.

Implementation is complete; installation, real allocator and decode acceptance
remain pending. Profile 8.1 success alone will not establish HDR color accuracy,
protected playback or encoder-stream correctness. No camera is activated by
these layout and offscreen decode checks.
