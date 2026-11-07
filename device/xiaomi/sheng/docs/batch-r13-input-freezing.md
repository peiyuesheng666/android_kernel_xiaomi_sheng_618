# Freezing r13 inputs

Run `tools/freeze_sheng_batch_inputs.py` from the synced ROM device tree only after
the Android build has completed successfully. Supply explicit Linux paths with
`--workspace` and `--output`; the output parent must exist, and an existing JSON
is never overwritten. This command creates a specification without packaging or
accessing USB.

The specification freezes the installed files, the FPC link text and original
blob hash, all reviewed tracked device sources outside `docs`, complete framework
overlay sources, the packaging tools, compiled file contexts and both EROFS image
property files. Workspace and ROM source hashes must agree. Generated vendor ART
properties and direct-install XML/defaults/init bytes are checked.

New nodes are inferred from the pinned baseline metadata. Labels come from the
same compiled context bytes used by the packer, looked up through libselinux;
existing EROFS inode labels must remain unchanged. The system delta adds only
`etc/device-config-defaults`. A temporary specification must pass `load_spec`
before the final JSON is published atomically without replacement.

The native lookup accepts the type names supported by compiled policy,
including the stock Qualcomm `vendor_diag-router_exec` label. Restricting type
names to underscores would incorrectly reject this valid existing inode.
