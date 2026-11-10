param([switch]$Flash)
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$evidence = Join-Path $workspace 'reports/device/r38-restore-20261110'
$manifest = Get-Content -Raw (Join-Path $evidence 'restore-manifest.json') | ConvertFrom-Json
if ($manifest.revision -ne 38 -or $manifest.target -ne 'ca10ede3/sheng' -or
    $manifest.restore_slot -ne 'a' -or $manifest.complete_avb_chain_verified -ne $true -or
    $manifest.userdata_erase_authorized -ne $false -or @($manifest.files).Count -ne 14) {
    throw 'Wrong restore manifest.'
}
$verifier = Join-Path $PSScriptRoot 'verify_sheng_r38_restore.py'
if ((Get-FileHash $verifier -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.source_sha256) {
    throw 'Restore verifier changed.'
}
$logical = @('product','system_ext','odm','system','vendor','vendor_dlkm','system_dlkm')
$physical = @('vendor_boot','dtbo','init_boot','boot','recovery','vbmeta_system','vbmeta')
if ((($manifest.files.partition | Sort-Object) -join ',') -ne
    ((($logical + $physical) | Sort-Object) -join ',')) { throw 'Unexpected partition set.' }
$images = @{}
foreach ($entry in $manifest.files) {
    if ($entry.path -notmatch '^artifacts/system-hardware-followup-sheng-r(30|32|36|38|38-restore)/[a-z_]+\.img$' -or
        [IO.Path]::GetFileName($entry.path) -ne ($entry.partition + '.img')) { throw 'Unexpected image path.' }
    if ($entry.path.Contains('r38-restore/') -and $entry.partition -ne 'vbmeta') { throw 'Unexpected restore delta.' }
    $path = Join-Path $workspace $entry.path
    if ((Get-Item $path).Length -ne $entry.bytes -or
        (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) {
        throw "Image changed: $($entry.partition)"
    }
    $images[$entry.partition] = $path
}
Write-Output 'Complete r38 restore preflight passed; target ca10ede3/sheng, slot a.'
if (-not $Flash) { return }
$backup = Join-Path $workspace 'artifacts/stock-before-r38-20261110'
$saved = @(Get-Content -Raw (Join-Path $backup 'manifest.json') | ConvertFrom-Json)
if ($saved.Count -ne 7) { throw 'Missing stock boot-chain backup.' }
foreach ($entry in $saved) {
    $path = Join-Path $backup $entry.name
    if ((Get-Item $path).Length -ne $entry.bytes -or
        (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) {
        throw 'Stock boot-chain backup changed.'
    }
}
$adb = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastboot = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$log = Join-Path $evidence 'restore-operations.txt'
function Invoke-Target([string]$tool, [string[]]$arguments) {
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $tool
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($argument in (@('-s','ca10ede3') + $arguments)) { $start.ArgumentList.Add($argument) }
    Add-Content $log ((Get-Date -Format o) + ' ' + [IO.Path]::GetFileName($tool) + ' ' + ($arguments -join ' '))
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    if (-not $process.Start()) { throw 'Tool failed to start.' }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $timeout = if ($arguments[0] -eq 'flash') {300000} else {20000}
    if (-not $process.WaitForExit($timeout)) { $process.Kill(); throw 'Device tool timeout.' }
    $output = $stdout.Result + "`n" + $stderr.Result
    $code = $process.ExitCode
    $process.Dispose()
    Add-Content $log $output
    if ($code -ne 0) { throw $output }
    return $output
}
function Assert-Fastboot([bool]$userspace) {
    if ((Invoke-Target $fastboot @('getvar','product')) -notmatch '(?m)^product:\s*sheng\s*$' -or
        (Invoke-Target $fastboot @('getvar','current-slot')) -notmatch '(?m)^current-slot:\s*a\s*$') {
        throw 'Fastboot target/slot mismatch.'
    }
    $expected = if ($userspace) {'yes'} else {'no'}
    if ((Invoke-Target $fastboot @('getvar','is-userspace')) -notmatch ('(?m)^is-userspace:\s*' + $expected + '\s*$')) {
        throw 'Wrong fastboot mode.'
    }
}
function Wait-Fastboot([bool]$userspace) {
    $deadline = (Get-Date).AddSeconds(120)
    do {
        Start-Sleep -Seconds 3
        try { Assert-Fastboot $userspace; return } catch { $lastFailure = $_ }
    } while ((Get-Date) -lt $deadline)
    throw $lastFailure
}
if ((Invoke-Target $adb @('shell','getprop ro.product.device')).Trim() -ne 'sheng' -or
    (Invoke-Target $adb @('shell','getprop ro.boot.slot_suffix')).Trim() -ne '_a' -or
    (Invoke-Target $adb @('shell','getprop ro.build.fingerprint')).Trim() -ne
        'Xiaomi/sheng/sheng:16/BP2A.250605.031.A3/OS3.0.303.0.WNXCNXM:user/release-keys' -or
    (Invoke-Target $adb @('shell','getprop sys.boot_completed')).Trim() -ne '1' -or
    (Invoke-Target $adb @('shell','getprop ro.boot.flash.locked')).Trim() -ne '0') {
    throw 'Expected running, unlocked stock A-slot tablet.'
}
Invoke-Target $adb @('reboot','fastboot') | Write-Output
Wait-Fastboot $true
# Shrink the stock product first to release super space for the complete set.
foreach ($p in $logical) {
    Write-Output "Flashing ${p}_a"
    Invoke-Target $fastboot @('flash',($p + '_a'),$images[$p]) | Write-Output
}
Invoke-Target $fastboot @('reboot','bootloader') | Write-Output
Wait-Fastboot $false
if ((Invoke-Target $fastboot @('getvar','unlocked')) -notmatch '(?m)^unlocked:\s*yes\s*$') {
    throw 'Bootloader is locked.'
}
foreach ($p in $physical) {
    Write-Output "Flashing ${p}_a"
    Invoke-Target $fastboot @('flash',($p + '_a'),$images[$p]) | Write-Output
}
Invoke-Target $fastboot @('reboot') | Write-Output
Write-Output 'Complete r38 set written to A. Userdata and metadata were not erased. Runtime verification remains required.'
