# Xiaomi Pad 6S Pro kernel

Linux 6.18.32 for Xiaomi Pad 6S Pro (sheng, Snapdragon 8 Gen 2).
Built and tested on HyperOS OS4.0.2.0.XPYCNXM.

[中文说明](README.zh-CN.md) · [Download](https://github.com/peiyuesheng666/android_kernel_xiaomi_sheng_618/releases/latest) · [Build guide](docs/BUILD.zh-CN.md)

## Completed changes

- Restored Qualcomm WALT scheduling and CPU frequency scaling.
- Integrated the stylus fixes and stock pen charging status interfaces.
- Restored the necessary thermal and charging interfaces.
- Fixed CPU deep-idle compatibility.

The installed kernel passed a ten-minute screen-off charging retest with the same CUKTECH power bank.
Power decreased smoothly; the user reported a displayed minimum of about 60 W.
The device used its existing system thermal configuration.
Source replay, module ABI/BTF, boot image and AVB checks passed.

## Downloads

| File | Contents |
| --- | --- |
| Image | Kernel image with embedded modules |
| boot.img | Complete boot image |
| sheng-kernel-source.tar.gz | Build project and complete fixed source input |
| SHA256SUMS | Release file checksums |

The release also includes a project ZIP, separate build input and a Git history bundle.
Toolchains and the matching stock boot template are listed in the [build guide](docs/BUILD.zh-CN.md).

[Features](docs/FEATURES.zh-CN.md) · [Source provenance](docs/PROVENANCE.zh-CN.md) · [Checks](docs/VALIDATION.zh-CN.md) · [Change history](docs/HISTORY.md)
