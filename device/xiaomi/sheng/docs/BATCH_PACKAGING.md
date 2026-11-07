# Reviewed r13 development batch

This device-owned helper updates the verified running image chain with the
generic fullscreen configuration, ARM64 ART properties, FPC loader alias/data
labeling, and the two stock color configuration files. It accepts exactly
system, ODM and vendor filesystem stages and publishes five images including
both vbmeta parents. Input and output scope are explicit in the reviewed JSON;
keyboard, touch and system_ext candidates are not installed by this batch.

`tools/package_sheng_batch_followup.py` requires exact installed build paths,
sizes and SHA256, device-source hashes, both EROFS image-info inputs and the
combined file-contexts input. `--validate-only` verifies these and the baseline
hashes and parent descriptors without creating a candidate. Normal packaging
verifies every stage before publishing the complete image directory.

EROFS updates retain existing file contents, inode metadata, xattrs and UUID
outside the declared delta. The new FPC alias is an actual relative symlink,
not a copied library. Its link text and existing target blob are separately
hash-frozen, and readback verifies the link and unchanged target. ext4 updates
retain existing inode metadata and superblock bytes, check the explicit new
node metadata and run read-only e2fsck. Both AVB parent chains retain their
keys and unrelated descriptors.

The vendor policy files, ODM precompiled policy and its three mapping markers
are part of the frozen batch. Their matching installed system/product/system_ext
markers must be checked after compilation and before flashing; the unused
system_ext image is not silently refreshed to satisfy a cache mismatch.

On drvfs, `renameat2(RENAME_NOREPLACE)` can return EINVAL. The helper falls back
only for EINVAL/ENOTSUP on a confirmed drvfs mount. A fixed PowerShell script
reads absolute sibling paths as UTF-8 JSON data on stdin and uses native
`Directory.Move`. Existing targets, including dangling reparse points and
targets created during the final check, are rejected without overwrite. The
helper never publishes individual images separately.

Validation completed on 2026-11-07:

- 12 synthetic filesystem/input/AVB cases passed, including unsafe link targets,
  changed inputs, real EROFS symlink readback and unchanged blob metadata.
- C-drive publication: all 11 cases passed.
- Linux ext4 publication: seven passed, four Windows-specific cases skipped.
- Artifacts junction resolving to E: nine passed; two reparse-creation fixtures
  could not create their test objects (Win32 1392) and were explicitly skipped.
  The corresponding rejection behavior was tested on C. This does not claim
  that those E-drive fixtures ran successfully.
- Independent source review repeated the 12 stage and 11 Windows cases.
- Python and PowerShell syntax and Git whitespace checks passed.

These fixtures use small disposable files; they are not a real image or boot
test. Actual compilation, packaging hashes and hardware results are recorded
separately.

`tools/flash_sheng_batch_followup.ps1` defaults to local image verification.
Its explicit `-Flash` mode additionally checks the authorized serial, sheng
identity, root endpoint, slot b and six installed baseline hashes before
entering fastbootd. It rechecks userspace mode, product and slot before writing
the three filesystem images and then their two parent images. It does not
change the active slot or erase user data.
