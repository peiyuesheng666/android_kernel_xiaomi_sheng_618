# r22 Settings resource references

The r21 About-device crash is the missing DeviceNamePreferenceController in
MyDeviceInfoFragment.onAttach. Both overlay-local and externally linked Settings
resources used 0x7f, so the overlay dynamic reference table rewrote Settings
attributes as local IDs. This also affects external titles and layouts.

Two rejected candidates were tested without replacing the installed static RRO:
--shared-lib preserves external IDs but produces package 0x00, which idmap2
rejects; an ordinary package 0x80 preserves Settings attributes but its local
string references are not dynamically rewritten (Resources.NotFoundException).
Neither candidate is suitable for installation.

The final device RRO uses AAPT2 --package-id 0x80 and contains no references to
its own resources. Settings references retain absolute 0x7f IDs, Lineage and
Android references retain their external mappings. Labels are XML literals in
default and Chinese XML variants. Color arrays contain literal labels in their
language variants. The numeric model controller remains upstream and reports
Build.MODEL; the separate model-name row displays Xiaomi Pad 6S Pro 12.4.

Host idmap2 creation, with overlayable enforcement enabled, passed. A temporary
idmap in an isolated process on ca10ede3 reads 10 and 4 controllers in the two
pages, both Chinese labels, the marketing name, and the original Chinese color
labels. Final compiled APK validation and actual page startup remain required.
The temporary resources do not replace the installed overlay.

## Final acceptance

The final compiled artifacts and r22 runtime checks passed. See
r22-runtime-20261107.md for ordinary-UID results, user confirmation and the
precise default-name validation scope.
