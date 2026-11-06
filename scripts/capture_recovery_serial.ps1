param(
    [string]$Port = '',
    [int]$TimeoutMinutes = 120,
    [switch]$Hold,
    [switch]$ContinueNow
)
$ErrorActionPreference = 'Stop'
$taskWorkspace = Split-Path -Parent $PSScriptRoot
$taskFolder = Join-Path $taskWorkspace 'reports\serial'
New-Item -ItemType Directory -Path $taskFolder -Force | Out-Null
$taskStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$taskOutput = Join-Path $taskFolder ('sheng-r3-' + $taskStamp + '.log')
$taskEvents = Join-Path $taskFolder ('sheng-r3-' + $taskStamp + '.events.txt')
$taskStatePath = Join-Path $taskFolder 'capture-state.json'
if (Test-Path -LiteralPath $taskStatePath) {
    try {
        $taskPrevious = Get-Content -LiteralPath $taskStatePath -Raw | ConvertFrom-Json
        $taskPreviousProcess = Get-CimInstance Win32_Process -Filter ('ProcessId=' + [int]$taskPrevious.pid)
        if ($taskPreviousProcess -and $taskPreviousProcess.CommandLine -like '*capture_recovery_serial.ps1*') {
            Write-Output ('Collector already running; log: ' + $taskPrevious.log)
            exit 0
        }
    } catch { }
}
$taskState = @{pid=$PID;state='waiting-for-sheng-usb-serial';log=$taskOutput;events=$taskEvents;started_at=(Get-Date -Format o);bytes=0}
function Save-TaskState {
    $taskTemporary = $taskStatePath + '.tmp'
    $taskState | ConvertTo-Json | Set-Content -LiteralPath $taskTemporary -Encoding UTF8
    Move-Item -LiteralPath $taskTemporary -Destination $taskStatePath -Force
}
function Task-Event([string]$Message) {
    ((Get-Date -Format o) + ' ' + $Message) | Add-Content -LiteralPath $taskEvents
}
Save-TaskState
Task-Event 'Collector started; device must be temporarily booted manually. No fastboot or flash commands are executed.'
$taskDeadline = (Get-Date).AddMinutes($TimeoutMinutes)
while ((Get-Date) -lt $taskDeadline) {
    $taskSelected = $Port
    if (-not $taskSelected) {
        $taskCandidates = @(Get-CimInstance Win32_SerialPort | Where-Object { $_.PNPDeviceID -match 'VID_1D6B&PID_0104' })
        if ($taskCandidates.Count -eq 1) { $taskSelected = $taskCandidates[0].DeviceID }
    }
    if (-not $taskSelected) { Start-Sleep -Milliseconds 500; continue }
    $taskSerial = New-Object System.IO.Ports.SerialPort($taskSelected,115200,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
    $taskSerial.Handshake = [System.IO.Ports.Handshake]::None
    $taskSerial.DtrEnable = $true
    $taskSerial.ReadTimeout = 500
    $taskSerial.WriteTimeout = 1000
    $taskSerial.ReadBufferSize = 65536
    $taskFile = $null
    try {
        $taskSerial.Open()
        $taskFile = [System.IO.File]::Open($taskOutput,[System.IO.FileMode]::Append,[System.IO.FileAccess]::Write,[System.IO.FileShare]::ReadWrite)
        $taskState.state='capturing'; $taskState.port=$taskSelected; Save-TaskState
        Task-Event ('Connected ' + $taskSelected)
        $taskConnectedAt = Get-Date
        $taskGoSent = $false
        $taskSawHold = $false
        $taskTail = ''
        $taskBuffer = New-Object byte[] 65536
        $taskLastState = Get-Date
        while ((Get-Date) -lt $taskDeadline -and $taskSerial.IsOpen) {
            try {
                $taskCount = $taskSerial.Read($taskBuffer,0,$taskBuffer.Length)
                if ($taskCount -gt 0) {
                    $taskFile.Write($taskBuffer,0,$taskCount)
                    $taskFile.Flush()
                    $taskState.bytes += $taskCount
                    $taskTail += [System.Text.Encoding]::UTF8.GetString($taskBuffer,0,$taskCount)
                    if ($taskTail.Contains('HOLD before Android init')) { $taskSawHold=$true }
                    if ($taskTail.Length -gt 8192) { $taskTail=$taskTail.Substring($taskTail.Length-8192) }
                }
            } catch [System.TimeoutException] { }
            if (-not $Hold -and -not $taskGoSent -and ($taskSawHold -or $ContinueNow) -and ((Get-Date) - $taskConnectedAt).TotalSeconds -ge 5) {
                $taskSerial.Write("GO`n")
                $taskGoSent=$true
                Task-Event 'Sent GO: continue from diagnostic PID1 to the original Lineage init.'
            }
            if (((Get-Date) - $taskLastState).TotalSeconds -ge 2) { Save-TaskState; $taskLastState=Get-Date }
        }
    } catch {
        Task-Event ($taskSelected + ': ' + $_.Exception.Message)
    } finally {
        if ($taskFile) { $taskFile.Dispose() }
        if ($taskSerial.IsOpen) { $taskSerial.Close() }
        $taskSerial.Dispose()
        $taskState.state='waiting-for-reconnect'; Save-TaskState
    }
    Start-Sleep -Milliseconds 500
}
$taskState.state='collector-timeout'; $taskState.finished_at=Get-Date -Format o
Save-TaskState
Task-Event 'Collector deadline reached.'
