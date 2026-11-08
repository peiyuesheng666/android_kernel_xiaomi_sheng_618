# Source and binary release requirements

On 2026-11-08 the user clarified that applications and system integration
must be written in this device tree. Open-source recognition engines are
allowed dependencies. The project is intended for a later GitHub release;
this does not authorize publishing or pushing it now.

For each adopted component, record its upstream project, immutable revision,
download location, checksum, covered files, license and any local changes.
Keep upstream copyright and attribution statements, complete license texts
and applicable NOTICE files. Modified upstream files must be identified as
modified. Newly authored code has its own stated license; its license does
not replace the licenses of dependencies.

Review model weights separately from implementation code. A permissively
licensed inference runtime does not establish permission to redistribute a
model. Preserve the model's own license and upstream statement of scope.
Dependencies with unclear redistribution terms remain excluded. Do not
substitute a paper citation or public download link for a license grant.

Before distributing an application or native library, inventory its actual
bundled and statically linked dependencies, including the C++ runtime. Ship
their required license texts/notices in the binary package as well as the
source tree. Document any corresponding-source or other obligations imposed
by adopted licenses and satisfy them in the relevant distribution. An AAR's
top-level Apache identifier alone is insufficient to review its bundled code.

For large permitted dependencies, prefer a reproducible checksum-pinned fetch
and build manifest over committing downloaded binaries. Keep the license and
provenance records reviewable in Git. A release must fail if a required notice,
source record or expected checksum is missing. Do not silently fetch a new tip.

The existing device tree contains OEM binaries and firmware references.
Recording their source is not a redistribution license. The eventual public
release needs a separate file inventory and review of these existing inputs;
where appropriate, publish extraction/build instructions and require the user
to supply a lawful firmware input instead of uploading proprietary payloads.
The whole repository is not currently certified as ready for public release.

Do not include signing private keys/passwords, raw device logs, face templates,
camera frames, screenshots, tokens or other private runtime evidence in the
public source or application release. Curated test receipts contain only the
minimum non-sensitive verification information. Release packaging must check
its tracked-file inventory and application archive contents.

The initial ShengFaceLab source uses Apache-2.0 and the ordinary Android SDK.
It contains no third-party recognition implementation or trained model. Its
own module license is interfaces/biometrics/softwareface/LICENSE. Its first
trial failed to complete enrollment; see software-face-lab-20261108.md.
OpenCV/YuNet/SFace are under review as subsequent engine candidates. That
review does not itself mean their binaries have been integrated or cleared
for distribution.
