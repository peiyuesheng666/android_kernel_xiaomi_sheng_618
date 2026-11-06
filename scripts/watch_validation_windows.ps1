param([Parameter(Mandatory=$true)][string]$RunId)
$ErrorActionPreference = 'Stop'
$taskWorkspace = Split-Path -Parent $PSScriptRoot
$taskEvent = '\\wsl.localhost\Ubuntu-22.04\root\sheng-lineage\logs\build-event.json'
$taskReport = Join-Path $taskWorkspace 'reports/validation-continuation-windows.json'
$taskRecord = @{ validation_run_id=$RunId; pid=$PID; action='waiting-for-validation'; started_at=(Get-Date -Format o) }
function Save-TaskRecord {
    $taskRecord | ConvertTo-Json | Set-Content -LiteralPath $taskReport -Encoding utf8
}
Save-TaskRecord
while ($true) {
    try { $taskState = Get-Content -LiteralPath $taskEvent -Raw | ConvertFrom-Json }
    catch { Start-Sleep -Seconds 2; continue }
    if ($taskState.run_id -ne $RunId) {
        $taskRecord.action='another-run-already-started'; Save-TaskRecord; exit 0
    }
    if ($taskState.state -ne 'running') { break }
    Start-Sleep -Seconds 2
}
if (-not $taskState.succeeded -or $taskState.phase -ne 'prebuild-validation-passed') {
    $taskRecord.action='validation-needs-repair'; Save-TaskRecord; exit 1
}
$taskRecord.action='handing-off-to-validated-linux-controller'; Save-TaskRecord
$taskLinuxScript = '/mnt/c' + (($taskWorkspace.Substring(2) + '/scripts/continue_after_validation.py') -replace '\\','/')
& wsl.exe -d Ubuntu-22.04 -- python3 $taskLinuxScript --run-id $RunId
$taskCode = $LASTEXITCODE
$taskRecord.action='linux-controller-exited'
$taskRecord.returncode=$taskCode
$taskRecord.finished_at=Get-Date -Format o
Save-TaskRecord
exit $taskCode
