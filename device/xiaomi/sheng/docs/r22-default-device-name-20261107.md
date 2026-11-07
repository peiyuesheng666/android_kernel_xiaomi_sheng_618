# r22 device name initialized after reset

The pinned SettingsProvider DatabaseHelper initializes Global.DEVICE_NAME from
def_device_name_simple, and its legacy migration uses def_device_name. Both
normally format Build.MODEL. The device-owned static provider RRO maps both to
the literal Xiaomi Pad 6S Pro 12.4 using resourcesMap inline strings. Inline
mappings apply across target locale variants rather than losing to a more
specific localized target string.

Host idmap2 creation passed with overlayable enforcement. An isolated on-device
resource load formatted both resources with the numeric model in 272 locale
cases; all returned the marketing name. Final installed resources will also be
checked from an ordinary application UID. No factory reset, data erasure or
replacement of an existing user-edited device name is part of this validation.
Build.MODEL remains 24018RPACC; ro.product.marketname remains the marketing name.
