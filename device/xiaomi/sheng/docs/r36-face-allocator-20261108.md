# Face image-reader allocator dependency

r35 seven-partition and policy-file readback passed. The user's attempt opened
camera 1 and entered frame processing, then mifaced aborted while its image-reader
BufferQueueProducer first allocated a GraphicBuffer. The fatal message was
"Failed to load matching allocator for mapper version 4". At the same point,
hal_miface_default was denied Binder calls to servicemanager and HIDL lookup of
hal_graphics_allocator_hwservice. The AIDL face frontend later aborted on a
failed HIDL call to the dead implementation. This explains the black preview;
r35 resolved the reverse camera callback but did not complete enrollment.

Declare the implementation as a standard hal_graphics_allocator client. The
pinned platform's allocator client policy provides service discovery, Binder
calls and allocator buffer sharing. The implementation already uses libui and
libmediandk to allocate its image-reader buffers; mapper lookup and allocator fd
use alone did not express this dependency. No graphics service, public library,
face executable or biometric security checks are changed. Compilation, exact
permission review and runtime acceptance remain pending.

Evidence: reports/device/r35-face-runtime-20261108/crash.txt and
logcat-after-attempt.txt. Original secure-world initialization succeeded on the
daemon's restart; no secure-world failure has been established by these logs.
