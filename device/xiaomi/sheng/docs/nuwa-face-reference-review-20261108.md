# nuwa face and camera reference review

The user's LineageOS nuwa reference was fetched read-only on 2026-11-08.
The remote default is `lineage-24.0` at
`8e2b6ca4375919035587115189760eed64f14b8d`. Its `lineage.dependencies` points
to `android_device_xiaomi_sm8550-common`, inspected at
`63da741c41384a23416159f148f7ef7c85c8ea61`. Both references are separate bare
repositories under `/root/sheng-612/reference`; no ROM checkout was replaced.

The complete device and common trees were searched at all five published
branches: lineage-22.2, 23.0, 23.1, 23.2 and 24.0. The nuwa extraction list
retains `odm/lib64/libmiface.so` and
`vendor/lib64/vendor.xiaomi.hardware.miface@1.0.so`. These are client/implementation
libraries, not service registration. The inspected product configuration,
VINTF, policies and Settings resources do not register the stock face HAL or
provide a face enrollment repair. Source presence cannot establish runtime
enrollment or authentication success.

There are two concrete camera adaptations worth comparing:

| Reference adaptation | sheng comparison |
| --- | --- |
| `camera.override_format_from_reserved=true` in common.mk | Already set in sheng/device.mk; no new change needed. |
| camera.xiaomi.so replaces its libui dependency with libui-v34.so | Addresses camera ABI compatibility. sheng already uses r25's reviewed GraphicBuffer allocation compatibility with current libui. The nuwa fixup does not apply to libmiface.so. |

The immutable camera fixup is in
[`extract-files.py`](https://github.com/LineageOS/android_device_xiaomi_nuwa/blob/8e2b6ca4375919035587115189760eed64f14b8d/extract-files.py#L64),
and the camera product setting is in
[`common.mk`](https://github.com/LineageOS/android_device_xiaomi_sm8550-common/blob/63da741c41384a23416159f148f7ef7c85c8ea61/common.mk#L116).
Do not switch sheng miface to a different libui merely because the camera
reference uses it: AImage/GraphicBuffer object ownership and ABI must agree
at both ends. No such dependency substitution is justified by this review.

The common display properties retain
`ro.surface_flinger.protected_contents=true`. They therefore do not provide
a protected-camera EGL import workaround matching the current r38 failure.
The independently prepared r39 candidate uses the platform's protected-client
blackout path; that is a sheng crash mitigation, not a nuwa-derived face fix.
It does not establish that the separate enrollment stall is repaired.

Nine immutable files passed Git blob identity checks. Branch commits, search
results and SHA256s are recorded in
`nuwa-face-reference-review-20261108.json`; raw snapshots remain outside Git
under `reports/device/nuwa-face-reference-20261108`. No foreign vendor blob was
imported, no public source was patched, no camera was opened and no image was
flashed during this comparison.
