#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0

MODDIR=${0%/*}
STATE="$MODDIR/state"
LOG="$MODDIR/service.log"
mkdir -p "$STATE" || exit 1
chmod 0700 "$STATE"
echo $$ > "$MODDIR/worker.pid"

log_event() {
  if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 65536 ]; then
    mv -f "$LOG" "$MODDIR/service.previous.log"
  fi
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"
}

# Runtime properties take precedence over persist.adb.tcp.port. Leave all
# persistent properties and ro.adb.secure/authentication policy untouched.
if [ ! -f "$STATE/saved" ]; then
  getprop service.adb.tcp.port > "$STATE/tcp-port"
  getprop service.adb.listen_addrs > "$STATE/listen-addrs"
  settings get global adb_enabled > "$STATE/adb-enabled" 2>/dev/null
  original_adb=$(cat "$STATE/adb-enabled")
  case "$original_adb" in
    0|1|null) ;;
    *) rm -f "$STATE/adb-enabled" ;;
  esac
  touch "$STATE/saved"
fi

cleanup() {
  sh "$MODDIR/restore.sh" >> "$LOG" 2>&1
  rm -f "$MODDIR/worker.pid"
}
trap cleanup EXIT
trap 'exit 0' HUP INT TERM

log_event "worker started; target tcp:5555"
settings_ready=0
while [ -d "$MODDIR" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ]; do
  changed=0
  if [ "$(getprop service.adb.tcp.port)" != 5555 ]; then
    setprop service.adb.tcp.port 5555 >> "$LOG" 2>&1
    changed=1
  fi
  if [ "$(getprop service.adb.listen_addrs)" != tcp:5555 ]; then
    setprop service.adb.listen_addrs tcp:5555 >> "$LOG" 2>&1
    changed=1
  fi

  if [ "$(getprop sys.boot_completed)" = 1 ]; then
    if [ "$settings_ready" = 0 ] || [ "$(settings get global adb_enabled 2>/dev/null)" != 1 ]; then
      if [ ! -f "$STATE/adb-enabled" ]; then
        settings get global adb_enabled > "$STATE/adb-enabled" 2>/dev/null
      fi
      if settings put global adb_enabled 1 >> "$LOG" 2>&1; then
        settings_ready=1
      fi
    fi
  fi

  if [ "$(getprop service.adb.tcp.port)" = 5555 ] &&
     [ "$(getprop service.adb.listen_addrs)" = tcp:5555 ]; then
    listener=$(awk '$2 ~ /:15B3$/ && $4 == "0A" { found=1 }
      END { if (found) print "ready"; else if (NR) print "missing"; else print "unknown" }' \
      /proc/net/tcp /proc/net/tcp6 2>/dev/null)
    if [ "$changed" = 1 ] || [ "$(getprop init.svc.adbd)" != running ] || [ "$listener" = missing ]; then
      if setprop ctl.restart adbd >> "$LOG" 2>&1; then
        log_event "requested adbd restart on tcp:5555 (listener: $listener)"
      else
        log_event "adbd restart failed; will retry"
      fi
    fi
  else
    log_event "ADB property update failed; will retry"
  fi
  sleep 15
done
log_event "module stopped; restoring previous ADB settings"
