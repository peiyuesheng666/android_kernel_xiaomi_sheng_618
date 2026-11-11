# Charging host tests

Run `bash scripts/test-charging.sh` after preparing the source cache. The runner
extracts production callbacks from the prepared r87 sources, compiles with
ASan/UBSan and runs fault injection. Generated files live under `dist/`.
Committed test.c files are archived test sources; the runner regenerates them.
Host firmware, workqueue, locking and parser shims do not replace device tests.
