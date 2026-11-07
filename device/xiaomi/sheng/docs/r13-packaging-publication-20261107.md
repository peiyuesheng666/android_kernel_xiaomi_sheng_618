# r13 packaging publication and Junction correction

The initial failure investigation was read-only. After the root agent safely
published and sealed r13, the child agent was authorized to correct only the
device-tree tools and temporary fixtures. Production images, the frozen r13 JSON,
and the device were not changed by that tool correction. Commits are owned by the
root agent.

## Observed failure

The log `/root/sheng-lineage/logs/sheng-r13-packaging-20261107.log` reaches final
publication after filesystem/readback, AVB, parent-chain and frozen-input checks.
Linux `renameat2(RENAME_NOREPLACE)` returns `EINVAL` on drvfs. The fixed Windows
publisher then exits with the captured message:

```text
Source and destination must be distinct siblings.
```

The root agent confirmed that the hidden publication staging directory contains
all five images and that their native Windows SHA256 values match its manifest.
The hidden directory is an ordinary directory; its parent `artifacts` is a
Junction to `E:\XiaomiPad6SProPort6.18-artifacts`.

The asymmetric `wslpath` results, captured by the root agent, explain the guard:

| Input state | Native mapping |
| --- | --- |
| Existing hidden stage below the C-side artifacts Junction | `E:\XiaomiPad6SProPort6.18-artifacts\.system-hardware-followup-sheng-r13-publishing` |
| Absent final directory below the same lexical C-side parent | `C:\Users\Dev裴月笙\Desktop\XiaomiPad6SProPort6.18\artifacts\system-hardware-followup-sheng-r13` |

JSON input was read successfully. The failure occurs in the publisher's parent
comparison, before `Directory.Move`. Its refusal preserves the verified stage
and does not create or overwrite the final directory.

## Safe reuse of the verified batch

The root agent selected the physical, common parent `/mnt/e/XiaomiPad6SProPort6.18-artifacts`
for the existing hidden stage and absent final directory, then called the existing
fixed `windows_directory_move` with those physical sibling paths. The whole
verified directory was published without changing frozen source, rebuilding an
image, recopying the batch, or rewriting its manifest. The root agent rechecked
all five native SHA256 values and the default flash verifier before flashing,
and reported matching partition hashes after reboot. The child investigation
did not execute this production retry or any device operation.

## Tool correction after sealing r13

The corrected helper maps the existing shared parent once with `windows_path(stage.parent)`. It constructs
both native child paths using `ntpath.join(parent, stage.name)` and
`ntpath.join(parent, destination.name)`. Keep the Linux sibling assertion and the
fixed PowerShell path, source, reparse and destination checks. An absent
destination is no longer separately passed to `wslpath`. No PowerShell script,
production image or frozen JSON change was needed for this correction.

The prior artifacts fixture called `Path.resolve()` on its parent before testing.
That converted the C-side Junction to the direct E-side path and concealed this
production difference.

The new fixture allocates dedicated C-side and E-side temporary directories,
creates a C-side Junction pointing to the E-side fixture, retains its lexical
C-side parent, and publishes the complete tiny batch through that alias. It
asserts that the old source/destination mappings differ, then verifies the new
publication through both alias and physical views, existing-target refusal and
competing-target refusal. General fixture parents now retain their lexical path
instead of being resolved before testing.

Native PowerShell verifies the Junction type, reparse attribute and resolved
target against the exact allocated E-side directory before a non-recursive
`Directory.Delete` removes only the link. It confirms the target is still present.
The two temporary roots are independently checked for resolved parent and
dedicated prefix before cleanup. Nothing is recursively deleted through the alias.

## Validation results

The interrupted turn had no test process left running. The completed C-side
12-test run was preserved; only the remaining lexical-artifacts and Linux runs
were executed afterward.

| Fixture parent | Results | Actual publication path |
| --- | --- | --- |
| C-side workspace with dedicated Junction to E-side temp | 12 passed, no skips | Windows native Directory.Move; old mapping mismatch asserted |
| Real lexical C-side artifacts Junction, retained without Path.resolve | 9 passed, 3 skipped | Windows native Directory.Move on its E-side common parent |
| `/tmp` | 7 passed, 5 skipped | Linux renameat2 with NOREPLACE; Windows fallback not called |

The real lexical artifacts run skips the dedicated C-side Junction case, already
covered by the first row. Its other two skips occur because the E volume rejects
fixture reparse creation with native Win32 error 1392; C-side dangling reparse
refusal is covered successfully in the first row. Linux skips the Windows-only
and cross-drive Junction cases. Copy/hash failures leave no final directory;
existing and competing targets remain unchanged. Only EINVAL/ENOTSUP may enter
the Windows fallback. Python syntax checks pass.

Tests only create tiny dedicated temporary data. The r13 production batch and
its frozen JSON are never test inputs or mutation targets.
