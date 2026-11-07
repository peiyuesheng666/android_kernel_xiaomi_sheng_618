# r14 rejected: composer initialization crash and verified r13 recovery

The user reported the first boot screen and correctly noted that Android/ADB
ports were already present. ADB readback confirmed that the kernel and partial
Android services were running, but sys.boot_completed was unset. The composer
restarted repeatedly with SIGSEGV at address 0x3 in stock libsdm-color.so,
ColorManager::RegisterDisplay+1004 (PC 0x3aa70, Build ID
75d569bf92904bf960c58a7630eb1887). SurfaceFlinger/framework startup could not
produce a usable display. This is a failed r14 hardware acceptance.

The installed core hash was the candidate 552309ea0473fff355e23d4679cba73f8b6ff179a183b7ccb912d7081c3a4593.
All three installed r14 image hashes matched the published images, excluding an
incorrect transfer as the observed cause. The crash occurs while walking the
formats map. The byte-only adapter test did not exercise C++ container
iteration or ownership and therefore was insufficient. Its success must not
be treated as proof of a usable ABI adapter. The old claim that copied map
pointers can simply be borrowed by a relocated byte view is rejected.

Evidence is retained under reports/device/r14-boot-failure: boot-and-crash.txt,
logcat-all.txt, composer-tombstone.txt and composer-tombstone.pb. No screenshot,
camera, biometric template, user-data erase or slot change was used.

The dedicated rollback helper verified the original r13 ODM/vendor/vbmeta
images, checked all six installed hashes and slot b, restored only those three
partitions through fastbootd, and rebooted. Its log is
reports/device/rollback-r14-20261107-155742/flash-and-reboot.txt.
Readback after recovery gave sys.boot_completed=1, stopped boot animation,
running composer and SurfaceFlinger, and all three original r13 hashes:

- ODM: 8f7fd6a31dfbd605032ee3dc3e27877eea063f90b082520d7fc2b306f194948b
- vendor: 7ca7ae03cc834d0928fa2ea140ab9b18232bf656a6ed28fccf0051ffb53f7753
- vbmeta: a05e23dce7886fe7fedc3049e05164012d61d9b9bebda0277826a4d00755b068

The user confirmed that both picture and touch returned to normal. r13 is the
current verified running baseline again; r14 images/spec/build records remain
preserved as failed evidence. The pending color and ambient features are not
marked repaired. Before another device trial, exercise real containers,
iteration and destruction in the ABI tests and review actual stock-library
consumption, including self-referential map sentinels.

## Follow-up candidate (not yet hardware accepted)

Disassembly of RegisterDisplay at 0x3aa20-0x3aaac shows the failed map traversal:
it compares nodes against the passed object's own end sentinel. A raw relocated
map header still refers to the original end sentinel. After the last element,
that old sentinel can be misread as a tree node and its map size (3 here) as a
pointer. Merely keeping the source object alive does not make the copied header
valid.

The next candidate owns a genuine PPHWAttributes C++ deep copy. It keeps the
resource prefix at that copy's constructed address, compacts only the suffix
in place for the stock call, then restores the native suffix and removed bytes
before C++ destruction. Copy and move of the temporary adapter are forbidden.
The real maps consequently retain matching sentinel addresses; its panel vector
owns an independent allocation and is restored before destruction.

The replacement sanitizer test constructs maps with 0, 1, 3 and 100 entries,
including nested vectors, iterates them to the actual end sentinel, verifies
independent node/vector ownership, exercises the compacted panel-vector view,
checks all nine feature versions/pointer/brightness, and then lets both copies
be destroyed. Address/undefined-behavior sanitizers pass. This is stronger host
coverage, but still does not establish acceptance by the actual stock library.
The failed r14 images/spec remain immutable and must not be reused as a fix.

The owned-copy candidate compiled and passed the native ELF checks in 01:38.
Before any new image, the explicit runtime helper tests only a temporary bind
of that one library over the running r13 file. It refuses an existing target
mount, requires the exact baseline/candidate hashes and keeps the on-disk image
unchanged. It watches the new composer PID, restores the verified original
library on early process death, and always restores it after at most 90 seconds.
Only its own recorded mount ID can be removed; a busy mount may be detached
lazily before restarting composer with the original file. No SELinux disabling,
data erase, camera use or forced GPU composition is part of this trial.
