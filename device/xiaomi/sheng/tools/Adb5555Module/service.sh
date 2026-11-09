#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0

MODDIR=${0%/*}
[ -f "$MODDIR/disable" ] && exit 0
[ -f "$MODDIR/remove" ] && exit 0
if [ -r "$MODDIR/worker.pid" ]; then
  old_pid=$(cat "$MODDIR/worker.pid")
  case "$old_pid" in
    ''|*[!0-9]*) ;;
    *)
      if [ -r "/proc/$old_pid/cmdline" ] &&
         tr '\000' ' ' < "/proc/$old_pid/cmdline" | grep -Fq "$MODDIR/worker.sh"; then
        exit 0
      fi
      ;;
  esac
fi
sh "$MODDIR/worker.sh" </dev/null >/dev/null 2>&1 &
