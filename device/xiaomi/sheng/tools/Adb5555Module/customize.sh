#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0

ui_print "Sheng ADB 5555: 启动时启用固定端口，保留 ADB 身份认证"
set_perm_recursive "$MODPATH" 0 0 0755 0644
for script in service.sh worker.sh restore.sh uninstall.sh; do
  set_perm "$MODPATH/$script" 0 0 0755
done
