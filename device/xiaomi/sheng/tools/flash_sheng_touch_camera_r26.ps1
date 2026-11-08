param([switch]$Flash, [switch]$VerifyRuntime)
$ErrorActionPreference = 'Stop'
if ($Flash -and $VerifyRuntime) { throw 'Select a single operation.' }
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$images = Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r26'
$serial = 'ca10ede3'
$baseline = @{
    system = '0f9c8ad6341faae4abaa9c080614d6d879aa62e85e36383086bb0333adfb4dce'
    system_ext = '82006f12228ebda0a521a96f8373c48bb52edb981a790830304f8ea50aa60419'
    odm = '933b205abe8bd856c62044a21e166097c288fadb56c18dd4c51099f104964ed7'
    vendor = '1033f2d63390dab9101d2fd97963d2a9f85cbcb872b71fb3f002c5b840fd29d3'
    vendor_dlkm = 'ade517337e3cef0cbb52eb1096ed46ceb98a97cec51b2d53c7f092c481ceae1f'
    vbmeta = '844a09d6781156bbc1a63fbe8f20abb12b4cb8cf713b4e1e434826d2063815a3'
    vbmeta_system = '3fe3413cc7fe8786372606ebfe7f9470e41bbf34b1dbcb5db7397540d9afc26a'
}
$manifestPath = Join-Path $images 'build-result.json'
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.revision -ne 26 -or $manifest.frozen_spec.revision -ne 26) { throw 'Wrong revision.' }
foreach ($key in @('exact_baselines_verified', 'all_filesystem_stages_verified',
    'three_changed_child_descriptors_verified', 'root_signature_verified',
    'root_other_descriptors_unchanged', 'original_systemui_required')) {
    if ($manifest.$key -ne $true) { throw "Missing packaging review: $key" }
}
$specPath = Join-Path $workspace 'device/xiaomi/sheng/docs/batch-r26-inputs-20261108.json'
if ((Get-FileHash -LiteralPath $specPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.spec_sha256) {
    throw 'Frozen specification changed.'
}
foreach ($entry in $manifest.frozen_spec.reviews_sha256.PSObject.Properties) {
    $path = Join-Path $workspace ('device/xiaomi/sheng/' + $entry.Name)
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw "Review changed: $($entry.Name)"
    }
}
$scope = @{odm=@('lib64/hw/camera.sheng.so'); vendor=@('build.prop'); vendor_dlkm=@('lib/modules/nt36532_touch.ko')}
if ((($manifest.frozen_spec.partitions.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'odm,vendor,vendor_dlkm') {
    throw 'Unexpected partition scope.'
}
foreach ($partition in $scope.Keys) {
    if ($manifest.baseline_sha256.$partition -ne $baseline[$partition] -or
        $manifest.frozen_spec.baseline_sha256.$partition -ne $baseline[$partition]) { throw 'Wrong baseline.' }
    $stage = $manifest.frozen_spec.partitions.$partition
    $report = $manifest.partition_reports.$partition
    $expected = ($scope[$partition] | Sort-Object) -join ','
    if ((($stage.files.PSObject.Properties.Name | Sort-Object) -join ',') -ne $expected -or
        (($report.changed_files | Sort-Object) -join ',') -ne $expected -or $report.metadata_preserved -ne $true) {
        throw "Unexpected filesystem scope: $partition"
    }
    $expectedNodes = if ($partition -eq 'odm') { 'lib64/hw/camera.sheng.so' } else { '' }
    if ((($stage.new_nodes.PSObject.Properties.Name | Sort-Object) -join ',') -ne $expectedNodes) { throw 'Unexpected new nodes.' }
}
if ($manifest.baseline_sha256.vbmeta -ne $baseline.vbmeta) { throw 'Wrong AVB root.' }
$sizes = @{odm=1141067776; vendor=303517696; vendor_dlkm=62590976; vbmeta=8192}
if (@($manifest.files).Count -ne 4 -or (($manifest.files.partition | Sort-Object) -join ',') -ne 'odm,vbmeta,vendor,vendor_dlkm') {
    throw 'Unexpected image set.'
}
$outputs = @{}
foreach ($file in $manifest.files) {
    $path = Join-Path $images $file.name
    $item = Get-Item -LiteralPath $path -Force
    if ($file.name -ne ($file.partition + '.img') -or $file.bytes -ne $sizes[$file.partition] -or
        $item.Length -ne $file.bytes -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
        throw "Image identity/hash mismatch: $($file.name)"
    }
    $outputs[$file.partition] = $file.sha256
}
Write-Output 'r26 exact file scope, reviewed inputs, image hashes and parent/child AVB checks passed.'
if (-not $Flash -and -not $VerifyRuntime) { return }
$adb = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastboot = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$evidence = Join-Path $workspace ('reports/device/r26-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $evidence | Out-Null
$log = Join-Path $evidence 'device-operations.txt'
function Invoke-Target([string]$tool, [string[]]$arguments) {
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $tool
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($argument in (@('-s', $serial) + $arguments)) { $start.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    if (-not $process.Start()) { throw 'Device tool failed to start.' }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $timeout = if ($arguments[0] -eq 'flash') { 180000 } else { 30000 }
    if (-not $process.WaitForExit($timeout)) { $process.Kill(); throw 'Device tool timed out.' }
    $text = $stdout.Result + "`n" + $stderr.Result
    $code = $process.ExitCode
    $process.Dispose()
    Add-Content -LiteralPath $log -Value $text -Encoding utf8
    if ($code -ne 0) { throw $text }
    return $text
}
if ((Invoke-Target $adb @('shell','getprop ro.product.device')).Trim() -ne 'sheng' -or
    (Invoke-Target $adb @('shell','getprop ro.boot.slot_suffix')).Trim() -ne '_b' -or
    (Invoke-Target $adb @('shell','getprop sys.boot_completed')).Trim() -ne '1' -or
    (Invoke-Target $adb @('shell','id -u')).Trim() -ne '0') {
    throw 'Wrong target, wrong slot, incomplete boot or non-root ADB. This script never runs adb root.'
}
$expected = @{} + $baseline
if ($VerifyRuntime) { foreach ($p in $outputs.Keys) { $expected[$p] = $outputs[$p] } }
foreach ($p in $expected.Keys) {
    $command = if ($p -in @('vbmeta','vbmeta_system')) {
        $bytes = if ($p -eq 'vbmeta') {8192} else {4096}
        "dd if=/dev/block/by-name/${p}_b bs=$bytes count=1 2>/dev/null | sha256sum"
    } else { "sha256sum /dev/block/mapper/${p}_b" }
    if ((Invoke-Target $adb @('shell',$command)) -notmatch ('(?m)^' + $expected[$p] + '\s')) { throw "Live partition mismatch: $p" }
}
if ((Invoke-Target $adb @('shell','sha256sum /system_ext/priv-app/SystemUI/SystemUI.apk')) -notmatch
    '(?m)^33017b0d59e28da5db3e089a98f49601de508228a012392ee2d04c82cda3ccb1\s') { throw 'Original SystemUI changed.' }
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $evidence 'packaging-manifest.json')
if ($VerifyRuntime) {
    foreach ($p in $scope.Keys) {
        foreach ($entry in $manifest.frozen_spec.partitions.$p.files.PSObject.Properties) {
            if ((Invoke-Target $adb @('shell',('sha256sum /' + $p + '/' + $entry.Name))) -notmatch
                ('(?m)^' + $entry.Value.sha256 + '\s')) { throw "Live file mismatch: $p/$($entry.Name)" }
        }
    }
    Invoke-Target $adb @('shell','getprop ro.hardware.camera; settings get secure adaptive_sleep; settings get system screen_off_timeout; getenforce; pidof com.android.systemui; pidof vendor.qti.camera.provider@2.7-service_64; dmesg | grep -E "NVT-ts|nt36532|firmware" | tail -70') | Write-Output
    Write-Output "Seven partition/file hashes verified; evidence: $evidence"
    return
}
Invoke-Target $adb @('reboot','fastboot') | Write-Output
$deadline = (Get-Date).AddSeconds(90)
$ready = $false
do {
    Start-Sleep -Seconds 3
    try { $ready = (Invoke-Target $fastboot @('getvar','is-userspace')) -match '(?m)^is-userspace:\s*yes\s*$' }
    catch { $ready = $false }
} until ($ready -or (Get-Date) -gt $deadline)
if (-not $ready -or (Invoke-Target $fastboot @('getvar','product')) -notmatch '(?m)^product:\s*sheng\s*$' -or
    (Invoke-Target $fastboot @('getvar','current-slot')) -notmatch '(?m)^current-slot:\s*b\s*$') { throw 'Target fastbootd identity mismatch.' }
foreach ($p in @('odm','vendor','vendor_dlkm','vbmeta')) {
    Invoke-Target $fastboot @('flash',($p + '_b'),(Join-Path $images ($p + '.img'))) | Write-Output
}
Invoke-Target $fastboot @('reboot') | Write-Output
Write-Output "r26 written to ca10ede3 / b; evidence: $evidence"
