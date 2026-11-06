param(
    [ValidateSet('vendor', 'odm', 'vbmeta')]
    [string[]]$Partitions = @('vendor', 'odm', 'vbmeta'),
    [string]$ImageDirectory = ''
)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$adbPath = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastbootPath = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$serial = 'ca10ede3'
$imageDirectory = if ($ImageDirectory) { [System.IO.Path]::GetFullPath($ImageDirectory) } else {
    Join-Path $workspace 'artifacts/system-bringup-sheng-r2'
}
$manifest = Get-Content -LiteralPath (Join-Path $imageDirectory 'build-result.json') -Raw | ConvertFrom-Json
$evidenceDirectory = Join-Path $workspace ('reports/device/system-bringup-r2-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $evidenceDirectory | Out-Null
$logPath = Join-Path $evidenceDirectory 'flash-and-boot.txt'

function Invoke-DeviceTool([string]$executable, [string[]]$arguments, [int]$timeoutMs = 60000) {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $executable
    $info.Arguments = ($arguments | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' }) -join ' '
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    if (-not $process.Start()) { throw 'Platform tool failed to start' }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($timeoutMs)) { $process.Kill(); throw 'Platform tool timed out' }
    $result = $stdout.Result + $stderr.Result
    Add-Content -LiteralPath $logPath -Value $result -Encoding UTF8
    if ($process.ExitCode -ne 0) { throw $result }
    return $result
}

foreach ($file in $manifest.files) {
    $image = Join-Path $imageDirectory $file.name
    if ((Get-Item -LiteralPath $image).Length -ne $file.bytes) { throw 'Image size changed' }
    if ((Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
        throw ('Image hash changed: ' + $file.name)
    }
}
foreach ($partition in $Partitions) {
    if ($partition -notin @($manifest.files.partition)) { throw ('No verified image for ' + $partition) }
}
$product = Invoke-DeviceTool $adbPath @('-s', $serial, 'shell', 'getprop ro.product.device')
$slot = Invoke-DeviceTool $adbPath @('-s', $serial, 'shell', 'getprop ro.boot.slot_suffix')
if ($product.Trim() -ne 'sheng' -or $slot.Trim() -ne '_b') { throw 'Device or active slot mismatch' }
if ($manifest.unchanged_odm_sha256) {
    $odmHash = Invoke-DeviceTool $adbPath @('-s', $serial, 'shell', 'sha256sum /dev/block/mapper/odm_b')
    if ($odmHash.Split()[0] -ne $manifest.unchanged_odm_sha256) {
        throw 'Installed ODM differs from the vbmeta reference; stop before flashing.'
    }
}
$before = Invoke-DeviceTool $adbPath @('-s', $serial, 'shell', 'getprop; getenforce; logcat -d -t 1500')
[System.IO.File]::WriteAllText((Join-Path $evidenceDirectory 'before.txt'), $before)
Write-Output 'Verified images and sheng b slot. Entering Fastbootd.'
Invoke-DeviceTool $adbPath @('-s', $serial, 'reboot', 'fastboot') | Out-Null
$deadline = (Get-Date).AddMinutes(3)
do {
    Start-Sleep -Seconds 3
    $devices = Invoke-DeviceTool $fastbootPath @('devices') 20000
} until ($devices -match '(?im)^ca10ede3\s+fastboot\s*$' -or (Get-Date) -gt $deadline)
if ($devices -notmatch '(?im)^ca10ede3\s+fastboot\s*$') { throw 'Fastbootd did not appear' }
$product = Invoke-DeviceTool $fastbootPath @('-s', $serial, 'getvar', 'product')
$slot = Invoke-DeviceTool $fastbootPath @('-s', $serial, 'getvar', 'current-slot')
$userspace = Invoke-DeviceTool $fastbootPath @('-s', $serial, 'getvar', 'is-userspace')
if ($product -notmatch '(?m)^product:\s*sheng\s*$' -or $slot -notmatch '(?m)^current-slot:\s*b\s*$' -or
    $userspace -notmatch '(?m)^is-userspace:\s*yes\s*$') { throw 'Fastbootd identity mismatch' }
if (($Partitions -contains 'vendor' -or $Partitions -contains 'odm') -and
    $Partitions -notcontains 'vbmeta') { throw 'Changed AVB partitions require matching vbmeta' }
foreach ($partition in @('vendor', 'odm', 'vbmeta') | Where-Object { $Partitions -contains $_ }) {
    Write-Output ('Flashing ' + $partition + '_b')
    Invoke-DeviceTool $fastbootPath @('-s', $serial, 'flash', ($partition + '_b'),
        (Join-Path $imageDirectory ($partition + '.img'))) 180000 | Write-Output
}
Invoke-DeviceTool $fastbootPath @('-s', $serial, 'reboot') | Out-Null
Write-Output 'Images flashed. Waiting for Android.'
$deadline = (Get-Date).AddMinutes(5)
$bootComplete = $false
do {
    Start-Sleep -Seconds 5
    $devices = Invoke-DeviceTool $adbPath @('devices') 20000
    if ($devices -match '(?im)^ca10ede3\s+device\s*$') {
        $boot = Invoke-DeviceTool $adbPath @('-s', $serial, 'shell', 'getprop sys.boot_completed')
        if ($boot.Trim() -eq '1') { $bootComplete = $true }
    }
} until ($bootComplete -or (Get-Date) -gt $deadline)
if (-not $bootComplete) { throw 'Boot verification timed out; check the saved flash log' }
Invoke-DeviceTool $adbPath @('-s', $serial, 'root') | Out-Null
Start-Sleep -Seconds 3
$rootIdentity = Invoke-DeviceTool $adbPath @('-s', $serial, 'shell', 'id')
$isRoot = $rootIdentity -match 'uid=0\(root\)'
foreach ($probe in @(
    @('after-properties.txt', 'getprop; getenforce; id; ps -AZ'),
    @('after-input.txt', 'dumpsys input'),
    @('after-window.txt', 'dumpsys window displays'),
    @('after-graphics.txt', 'dumpsys SurfaceFlinger'),
    @('after-camera.txt', 'dumpsys media.camera'),
    @('after-logcat.txt', 'logcat -d -t 2500'),
    @('after-kernel.txt', 'dmesg')
)) {
    if ($probe[0] -eq 'after-kernel.txt' -and -not $isRoot) {
        Add-Content -LiteralPath $logPath -Value 'Kernel diagnostics skipped: ADB root is unavailable.'
        continue
    }
    $output = Invoke-DeviceTool $adbPath @('-s', $serial, 'shell', $probe[1])
    [System.IO.File]::WriteAllText((Join-Path $evidenceDirectory $probe[0]), $output)
}
Write-Output ('Android boot_completed=1. Evidence: ' + $evidenceDirectory)
