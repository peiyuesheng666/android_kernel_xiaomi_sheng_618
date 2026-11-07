# Snapdragon Color configuration

`snapdragon_color_libs_config.xml` is an unchanged copy from the sheng stock
OS3.0.303.0.WNXCNXM Android 16 vendor partition. Its SHA256 is
`dd41f581cbd151bfbfe92f1db1ee80ebc12ed8c21851790d770d30fb3e0c4dea`.

The stock `libsnapdragoncolor-manager.so` reads this exact path:
`/vendor/etc/snapdragon_color_libs_config.xml`. The file registers the existing
QDCM and Xiaomi hardware modulation libraries in the original processing order.
Without it, the current composer lists only the Native fallback mode and does
not load either registered library.

Add `sheng_snapdragon_color_libs_config` to the product's package list when
integrating this module. Keep the existing per-panel QDCM JSON and LUT files
unchanged. The original panel JSON is already installed under `/odm/etc/display`
and matches stock SHA256
`5eff4bb9342cf499c7bc313ded7dea5eae70977068fdb9aa0029a98ffe193b70`.

Build and boot validation must check that the XML is installed at the exact
vendor path, both libraries load into the composer, and sRGB / Display P3 modes
are enumerated. Merely setting wide-color properties does not validate the
calibration. Check the visible result with the user before marking color
accuracy fixed.

The configuration loads during composer initialization. Removing this module
and rebuilding restores the prior state. Runtime mode changes alone do not
reload a missing initialization file.
