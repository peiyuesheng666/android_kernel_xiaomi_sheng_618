#requires -Version 7.0
$ErrorActionPreference='Stop'
$taskWorkspace=Split-Path -Parent $PSScriptRoot
$taskAdb=Join-Path $taskWorkspace 'tools\platform-tools\adb.exe'
$taskEvent='\\wsl.localhost\Ubuntu-22.04\root\sheng-lineage\logs\recovery-qti\build-event.json'
$taskFolder=Join-Path $taskWorkspace ('reports\device\qti-live-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $taskFolder -Force | Out-Null
$taskStatePath=Join-Path $taskWorkspace 'reports\device\qti-live-state.json'
$taskState=@{pid=$PID;state='waiting-for-qti-build';started_at=(Get-Date -Format o);logs=$taskFolder;serial='ca10ede3'}
function Save-TaskState {$taskState | ConvertTo-Json | Set-Content -LiteralPath $taskStatePath -Encoding utf8}
function Invoke-TaskAdb([string[]]$ToolArguments,[string]$InputText='', [int]$Timeout=30000) {
    $taskInfo=[System.Diagnostics.ProcessStartInfo]::new()
    $taskInfo.FileName=$taskAdb
    $taskInfo.UseShellExecute=$false
    $taskInfo.CreateNoWindow=$true
    $taskInfo.RedirectStandardOutput=$true
    $taskInfo.RedirectStandardError=$true
    $taskInfo.RedirectStandardInput=$true
    $taskInfo.ArgumentList.Add('-s');$taskInfo.ArgumentList.Add('ca10ede3')
    foreach($taskArgument in $ToolArguments){$taskInfo.ArgumentList.Add($taskArgument)}
    $taskChild=[System.Diagnostics.Process]::new();$taskChild.StartInfo=$taskInfo
    $null=$taskChild.Start()
    $taskOut=$taskChild.StandardOutput.ReadToEndAsync();$taskErr=$taskChild.StandardError.ReadToEndAsync()
    if($InputText){$taskChild.StandardInput.Write($InputText)}
    $taskChild.StandardInput.Close()
    if(-not $taskChild.WaitForExit($Timeout)){$taskChild.Kill();$taskChild.WaitForExit();throw 'Own adb child timed out'}
    $taskResult=@{code=$taskChild.ExitCode;stdout=$taskOut.GetAwaiter().GetResult();stderr=$taskErr.GetAwaiter().GetResult()}
    $taskChild.Dispose();return $taskResult
}
Save-TaskState
$taskDeadline=(Get-Date).AddMinutes(60)
while((Get-Date)-lt $taskDeadline){
    try {$taskBuild=Get-Content -LiteralPath $taskEvent -Raw | ConvertFrom-Json} catch {Start-Sleep -Seconds 1;continue}
    if($taskBuild.run_id -ne '2d8f1b686d6d4c8ba1084821b931c2a3'){throw 'Different source build; no live change'}
    if($taskBuild.state -ne 'running'){break}
    Start-Sleep -Seconds 1
}
if(-not $taskBuild.succeeded){$taskState.state='build-not-successful';Save-TaskState;exit 1}
& wsl.exe -d Ubuntu-22.04 -u root -- python3 ('/mnt/c'+$taskWorkspace.Substring(2).Replace([char]92,[char]47)+'/scripts/finalize_qti_candidate.py') > (Join-Path $taskFolder 'candidate-verification.txt') 2>&1
if($LASTEXITCODE){$taskState.state='candidate-verification-failed';Save-TaskState;exit 1}
$taskReceipt=Get-Content -LiteralPath (Join-Path $taskWorkspace 'reports\qti-candidate.json') -Raw | ConvertFrom-Json
$taskLocal=Join-Path $taskFolder 'librecovery_ui-qti.so'
Copy-Item -LiteralPath '\\wsl.localhost\Ubuntu-22.04\root\sheng-lineage\recovery-qti-candidate\librecovery_ui.so' -Destination $taskLocal
if((Get-FileHash -LiteralPath $taskLocal -Algorithm SHA256).Hash -ne $taskReceipt.sha256){throw 'Candidate copy SHA mismatch'}
$taskIdentity=Invoke-TaskAdb @('shell','getprop ro.sheng.recovery.diagnostic')
if($taskIdentity.stdout.Trim() -ne 'serial-to-adb-r5'){$taskState.state='different-device-state-refused';Save-TaskState;exit 1}
$taskCurrent=Invoke-TaskAdb @('shell','sha256sum /system/lib64/librecovery_ui.so')
if($taskCurrent.stdout -notmatch ('^'+$taskReceipt.original_sha256+'\s')){throw 'Running UI library differs from the known baseline'}
$taskPush=Invoke-TaskAdb @('push',$taskLocal,'/tmp/sheng-librecovery-ui-qti.so')
if($taskPush.code){throw $taskPush.stderr}
$taskState.state='applying-in-ram-ui-library';$taskState.sha256=$taskReceipt.sha256;Save-TaskState
$taskApply=@'
set -e
test "$(getprop ro.sheng.recovery.diagnostic)" = serial-to-adb-r5
case "$(awk '$2 == "/" { print $3 }' /proc/mounts)" in rootfs|tmpfs) ;; *) exit 20 ;; esac
mkdir -p /diag-update
if [ ! -f /diag-update/librecovery_ui-original.so ]; then cp /system/lib64/librecovery_ui.so /diag-update/librecovery_ui-original.so; fi
cp /tmp/sheng-librecovery-ui-qti.so /diag-update/librecovery_ui-qti.so
chmod 644 /diag-update/librecovery_ui-qti.so
stop recovery
if ! mount --bind /diag-update/librecovery_ui-qti.so /system/lib64/librecovery_ui.so; then start recovery; exit 21; fi
start recovery
sleep 3
getprop init.svc.recovery
getprop init.svc_debug_pid.recovery
sha256sum /system/lib64/librecovery_ui.so
'@
$taskApplied=Invoke-TaskAdb @('shell','sh','-s') $taskApply
($taskApplied.stdout+$taskApplied.stderr)|Set-Content -LiteralPath (Join-Path $taskFolder 'apply.txt')
if($taskApplied.code){$taskState.state='live-apply-failed';Save-TaskState;exit $taskApplied.code}
$taskState.state='qti-ui-library-running';Save-TaskState
Start-Sleep -Seconds 25
$taskDiagnostics=Invoke-TaskAdb @('shell','sh','-s') @'
echo ===STATE===
getprop init.svc.recovery
getprop init.svc_debug_pid.recovery
getprop sys.usb.state
echo ===RECOVERY_LOG===
cat /tmp/recovery.log
echo ===DMESG===
dmesg | tail -250
'@
($taskDiagnostics.stdout+$taskDiagnostics.stderr)|Set-Content -LiteralPath (Join-Path $taskFolder 'qti-diagnostics.txt') -Encoding utf8
$taskAfter=Invoke-TaskAdb @('shell','getprop init.svc.recovery')
if($taskAfter.stdout.Trim() -ne 'running'){
    $taskRollback=Invoke-TaskAdb @('shell','stop recovery; umount /system/lib64/librecovery_ui.so; start recovery')
    ($taskRollback.stdout+$taskRollback.stderr)|Set-Content -LiteralPath (Join-Path $taskFolder 'rollback.txt')
    $taskState.state='qti-failed-rolled-back'
}else{$taskState.state='qti-live-test-ready-for-screen-confirmation'}
$taskState.finished_at=Get-Date -Format o
Save-TaskState
$taskState|ConvertTo-Json
