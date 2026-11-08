# Camera orientation adapter (r26 candidate)

r25 restores preview but the user requests a 90-degree counterclockwise
correction. The board now selects camera.sheng, which loads the unchanged r25
camera.xiaomi module and forwards its camera operations. Only get_camera_info
and get_physical_camera_info substitute stable, read-only metadata clones.
The observed rear 90-degree mount becomes 0; front 270 becomes 180. Synthetic
zero-degree devices, external cameras and unrecognized mounting pairs remain
unchanged. The camera_info orientation matches the substituted static tag.

The adapter preserves the whole OEM 376-byte HMI object: a standard 344-byte
camera_module_t prefix and its opaque 32-byte tail. All reserved/extension
pointers are retained. open/open_legacy forward the original module pointer.
Vendor tags, callbacks, torch, stream checks, device-state callbacks, camera
processing and the existing GraphicBuffer repair are retained.

The isolated vendor compile/link passed using cached audited platform flags.
The source has normal Android.bp / PRODUCT_PACKAGES integration; a complete
new Soong/product build has not run because of host resource limits. The first
compile intentionally failed its module-size assertion; ELF review established
the OEM private tail and the final candidate preserves it explicitly.

On ca10ede3, a standalone test using only synthetic metadata and fake callbacks
passed 12 orientation cases, immutable OEM buffers, preserved unrelated tags,
error propagation, original-module forwarding and 1,600 concurrent cache reads.
It passed with both ordinary and vendor/ODM library search paths. No real camera
was loaded/opened, and no image was captured. Raw evidence is in
reports/device/r26-camera-orientation-20261108/synthetic-test.txt.

Build evidence: /root/sheng-lineage/hardware-diagnostics/r26-camera-orientation-attempt2/.
Exact source/output hashes are in r26-camera-orientation-review-20261108.json.
This is a candidate, not an installed repair or a user preview pass. Packaging,
AVB-chain review, provider startup and user direction validation remain pending.
