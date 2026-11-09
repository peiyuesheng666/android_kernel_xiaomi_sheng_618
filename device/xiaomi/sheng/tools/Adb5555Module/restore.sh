#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0

MODDIR=${0%/*}
STATE="$MODDIR/state"
[ -f "$STATE/saved" ] || exit 0
setprop service.adb.tcp.port "$(cat "$STATE/tcp-port")"
setprop service.adb.listen_addrs "$(cat "$STATE/listen-addrs")"
if [ "$(getprop init.svc.adbd)" = running ]; then
  setprop ctl.restart adbd
fi
