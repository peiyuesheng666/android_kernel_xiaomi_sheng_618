#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0

MODDIR=${0%/*}
touch "$MODDIR/remove"
if [ -r "$MODDIR/worker.pid" ]; then
  worker_pid=$(cat "$MODDIR/worker.pid")
  case "$worker_pid" in
    ''|*[!0-9]*) ;;
    *)
      if [ -r "/proc/$worker_pid/cmdline" ] &&
         tr '\000' ' ' < "/proc/$worker_pid/cmdline" | grep -Fq "$MODDIR/worker.sh"; then
        kill "$worker_pid"
      fi
      ;;
  esac
fi
sh "$MODDIR/restore.sh"
