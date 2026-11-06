#requires -Version 7.0
param(
    [Parameter(Mandatory=$true)][string]$Image,
    [Parameter(Mandatory=$true)][string]$ExpectedSha256,
    [int]$WaitMinutes=30,
    [string]$FastbootPath=''
)
$ErrorActionPreference='Stop'
$taskWorkspace=Split-Path -Parent $PSScriptRoot
$taskFastboot=Join-Path $taskWorkspace 'tools\platform-tools\fastboot.exe'
if ($FastbootPath) { $taskFastboot=(Resolve-Path -LiteralPath $FastbootPath).Path }
$taskAdb=Join-Path $taskWorkspace 'tools\platform-tools\adb.exe'
$taskImage=(Resolve-Path -LiteralPath $Image).Path
if ((Get-FileHash -LiteralPath $taskImage -Algorithm SHA256).Hash -ne $ExpectedSha256) {throw 'Temporary image checksum mismatch'}
$taskStamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$taskFolder=Join-Path $taskWorkspace ('reports\device\'+$taskStamp)
New-Item -ItemType Directory -Path $taskFolder -Force | Out-Null
$taskState=@{pid=$PID;image=$taskImage;image_sha256=$ExpectedSha256;state='waiting-for-fastboot';started_at=(Get-Date -Format o);logs=$taskFolder}
function Save-TaskState {
    $taskState | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskWorkspace 'reports\device\autoboot-state.json') -Encoding utf8
}
function Invoke-TaskTool([string]$Executable,[string[]]$ToolArguments,[int]$Timeout=10000,[string]$InputText='') {
    $taskInfo=[System.Diagnostics.ProcessStartInfo]::new()
    $taskInfo.FileName=$Executable
    $taskInfo.WorkingDirectory=Split-Path -Parent $taskImage
    $taskInfo.UseShellExecute=$false
    $taskInfo.CreateNoWindow=$true
    $taskInfo.RedirectStandardOutput=$true
    $taskInfo.RedirectStandardError=$true
    $taskInfo.RedirectStandardInput=$true
    foreach ($taskArgument in $ToolArguments) {$taskInfo.ArgumentList.Add($taskArgument)}
    $taskChild=[System.Diagnostics.Process]::new()
    $taskChild.StartInfo=$taskInfo
    $null=$taskChild.Start()
    $taskOut=$taskChild.StandardOutput.ReadToEndAsync()
    $taskErr=$taskChild.StandardError.ReadToEndAsync()
    if ($InputText) {$taskChild.StandardInput.Write($InputText)}
    $taskChild.StandardInput.Close()
    if (-not $taskChild.WaitForExit($Timeout)) {
        $taskChild.Kill()
        $taskChild.WaitForExit()
        throw ('Own tool timed out: '+$Executable+' '+($ToolArguments -join ' '))
    }
    $taskResult=@{code=$taskChild.ExitCode;stdout=$taskOut.GetAwaiter().GetResult();stderr=$taskErr.GetAwaiter().GetResult()}
    $taskChild.Dispose()
    return $taskResult
}
Save-TaskState
$taskDeadline=(Get-Date).AddMinutes($WaitMinutes)
$taskSerial=''
while ((Get-Date) -lt $taskDeadline) {
    $taskListed=Invoke-TaskTool $taskFastboot @('devices')
    $taskDevices=@($taskListed.stdout -split "`r?`n" | Where-Object {$_ -match '^([A-Za-z0-9_.:-]+)\s+fastboot\s*$'})
    if ($taskDevices.Count -eq 1) {
        $taskSerial=($taskDevices[0] -split '\s+')[0]
        $taskProduct=Invoke-TaskTool $taskFastboot @('-s',$taskSerial,'getvar','product')
        ($taskProduct.stdout+$taskProduct.stderr) | Set-Content -LiteralPath (Join-Path $taskFolder 'fastboot-product.txt')
        if (($taskProduct.stdout+$taskProduct.stderr) -notmatch 'product:\s*sheng(\s|$)') {
            $taskState.state='different-device-refused'; Save-TaskState; throw 'Connected bootloader is not sheng'
        }
        break
    }
    Start-Sleep -Milliseconds 500
}
if (-not $taskSerial) {$taskState.state='waiting-timeout';Save-TaskState;exit 2}
$taskState.serial=$taskSerial
$taskState.state='temporary-booting'
Save-TaskState
$taskBoot=Invoke-TaskTool $taskFastboot @('-s',$taskSerial,'boot',(Split-Path -Leaf $taskImage)) 45000
($taskBoot.stdout+$taskBoot.stderr) | Set-Content -LiteralPath (Join-Path $taskFolder 'fastboot-boot.txt')
$taskState.fastboot_returncode=$taskBoot.code
if ($taskBoot.code) {
    # A USB status read can fail during re-enumeration. Observe the resulting
    # device once without sending another boot or treating this as success.
    $taskState.fastboot_status_error=$taskBoot.stderr
}
$taskState.state='waiting-for-recovery-adb'
Save-TaskState
$taskAdbDeadline=(Get-Date).AddSeconds(120)
$taskConnected=$false
while ((Get-Date) -lt $taskAdbDeadline) {
    $taskConnection=Invoke-TaskTool $taskAdb @('-s',$taskSerial,'get-state') 5000
    if ($taskConnection.code -eq 0 -and $taskConnection.stdout.Trim() -in @('device','recovery')) {$taskConnected=$true;break}
    Start-Sleep -Milliseconds 500
}
if (-not $taskConnected) {$taskState.state='adb-not-available';Save-TaskState;exit 3}
$taskState.state='collecting-recovery-diagnostics'
Save-TaskState
$taskReadOnlyScript=@'
echo '=== KERNEL AND BUILD ==='
uname -a
id
getprop ro.product.device
getprop ro.sheng.recovery.diagnostic
getprop ro.sheng.recovery.variant
cat /proc/cmdline
getprop ro.debuggable
getprop ro.adb.secure
getprop init.svc.recovery
getprop init.svc.adbd
getprop sys.usb.config
getprop sys.usb.state
echo '=== PROCESSES ==='
ps -A
echo '=== RECOVERY LOG ==='
cat /tmp/recovery.log
echo '=== HARDWARE LOG ==='
cat /tmp/sheng-recovery-hardware.log
echo '=== DRM AND FRAMEBUFFER ==='
ls -l /dev/dri /dev/graphics /sys/class/drm
for p in /sys/class/drm/card*-*/status /sys/class/drm/card*-*/enabled /sys/class/drm/card*-*/modes; do echo "$p"; cat "$p"; done
cat /sys/kernel/debug/dri/0/state
echo '=== BACKLIGHT ==='
for p in /sys/class/backlight/*/brightness /sys/class/backlight/*/actual_brightness; do echo "$p"; cat "$p"; done
echo '=== RECOVERY STACK ==='
for p in $(pidof recovery); do cat /proc/$p/status; cat /proc/$p/wchan; cat /proc/$p/stack; done
echo '=== DMESG ==='
dmesg
'@
$taskDiagnostics=Invoke-TaskTool $taskAdb @('-s',$taskSerial,'shell','sh','-s') 30000 $taskReadOnlyScript
($taskDiagnostics.stdout+$taskDiagnostics.stderr) | Set-Content -LiteralPath (Join-Path $taskFolder 'recovery-diagnostics.txt') -Encoding utf8
$taskState.state='adb-diagnostics-collected'
$taskState.finished_at=Get-Date -Format o
$taskState.diagnostics_returncode=$taskDiagnostics.code
Save-TaskState
$taskState | ConvertTo-Json
