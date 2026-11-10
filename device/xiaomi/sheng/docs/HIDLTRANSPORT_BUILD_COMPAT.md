# Legacy face transport dependency

Regenerating the product's Soong graph on 2026-11-10 failed because the
device-owned `sheng-miface-service` referred directly to `libhidltransport`.
The manifest-pinned `system/libhidl` at
`061055fc4dad78e5d25a77d9217001794656f16b` restricts that deprecated module to
hardware/vendor source directories and system partitions. ODM modules defined
under a device directory are not covered by those visibility rules.

The public module is an empty compatibility library. The original face binary
still has its DT_NEEDED entry, so deleting the dependency or disabling ELF
verification would discard a useful check. The device supplies
`libsheng_hidltransport_link`, with SONAME `libhidltransport.so`, as an empty,
non-installable library for the existing prebuilt's ELF dependency check.
The service uses that unique Soong identity. The normal platform runtime file
remains installed through the existing generated vendor dependencies; there
is no second installation rule and no modified face binary. The tablet's
runtime file has SHA-256
`fd2f87a3902e3c6638654665035e8f4860dab6d51640e9a1e66006dafa56e9dc`
and exports no defined dynamic symbols.

Piano `8c0bb4b9d15ea349eaa09d6de0aa4fec43f7ff41`, nuwa
`8e2b6ca4375919035587115189760eed64f14b8d` and sm8550-common
`63da741c41384a23416159f148f7ef7c85c8ea61` were refreshed and searched. They
contain no corresponding device-owned dependency workaround; the pinned
public empty library and sheng's unchanged DT_NEEDED list determine this fix.
Public source visibility remains unchanged.

The regenerated product graph accepts this dependency. Because it is not
installable, its bare module name is not a Make build target; build its exact
Soong output when verifying the compatibility ELF. Raw build logs stay in
`reports/device/20261110-resume/dolby/`. This fixes build metadata and does not
establish face enrollment or unlock acceptance.
