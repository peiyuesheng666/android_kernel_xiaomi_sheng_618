# sheng device configuration — in progress

This is an independently written initial product configuration, not a completed
or boot-tested port. Board/product, HAL selection, properties, init, policy,
overlays and extraction are now standalone in this tree, with one sheng vendor
output. Official LineageOS kernel/modules/DT and hardware/xiaomi remain source
dependencies. The piano project is a reference
for product organization only; none of its files or kernel artifacts are used.

Stock input is OS3.0.303.0.WNXCNXM (Android 16), opened read-only outside this
tree. Its extracted vendor identifies Android 13 / SDK 33, while ODM reports
first API 34 and model 24018RPACC. Its super geometry is 11,811,160,064 bytes.
These are measurements of the supplied firmware, not guesses from another pad.

Prepared and checked:

- cp2a product entry, actual sheng partition geometry and source-kernel fragment.
- Stock DT/DTBO from the supplied package, installed outside its directory.
- Explicit standalone board and product settings, plus locally maintained
  Qualcomm helpers with their original licenses and provenance retained.
- Stock vendor extraction and generated build files; original files remain read-only.
- Actual audio routing/calibration, input layouts, FPC side-sensor properties,
  init permissions, initial SELinux rules and framework tablet overlay.
- A strict stock-module ABI installer; no vermagic modification or forced loads.
- Host dependencies, 80 GiB total swap, 24-way build and 10 GiB compressed ccache.

Outstanding validation before any full-build success can be claimed:

- Finish platform and official device dependency synchronization.
- Check board-module KMI and symbol CRC compatibility against the actual build;
  a matching 5.15 version alone
  does not establish compatibility with stock proprietary modules.
- Validate source/proprietary HAL ABI, permissions and policy during compilation,
  then refine power/display and tablet features with real hardware logs.
- Complete `m bacon`, validate image sizes, VINTF, ELF dependencies and packaging.
- Deliver artifacts for user hardware testing; no boot claim before that test.

PixelOS/Evolution X product entries are deferred until the LineageOS platform
and hardware configuration are stable.
