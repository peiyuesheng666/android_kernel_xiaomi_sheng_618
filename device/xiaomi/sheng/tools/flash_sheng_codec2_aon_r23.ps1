param([switch]$Flash)
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$images = Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r23'
$serial = 'ca10ede3'
$baselines = @{
    system = '0f9c8ad6341faae4abaa9c080614d6d879aa62e85e36383086bb0333adfb4dce'
    system_ext = '82006f12228ebda0a521a96f8373c48bb52edb981a790830304f8ea50aa60419'
    odm = 'c315f3e80f292909740d3e052102dcabb36b3f3bcaa817918f9dbc92630ce651'
    vendor = '210bf6f64bc865a8f6834e5b4b1d6fdd965139fec2cef2fda56b9fe978d5fd27'
    vbmeta = '37c3db81b769c3d872f04eee2ac778be77e70a5e47aa141a9e27215cafec6b4d'
    vbmeta_system = '3fe3413cc7fe8786372606ebfe7f9470e41bbf34b1dbcb5db7397540d9afc26a'
}
$manifest = Get-Content -Raw -LiteralPath (Join-Path $images 'build-result.json') | ConvertFrom-Json
$build = Get-Content -Raw -LiteralPath (Join-Path $workspace 'device/xiaomi/sheng/docs/build-r23-codec2-aon-20261107.json') | ConvertFrom-Json
if ($manifest.revision -ne 23 -or $manifest.frozen_spec.revision -ne 23 -or
    $build.build_passed -ne $true -or $build.helper_tests_passed -ne $true -or
    $build.upstream_audit_passed -ne $true) { throw 'Missing r23 build review.' }
foreach ($key in @('exact_baselines_verified', 'all_filesystem_stages_verified',
    'parent_chain_verified', 'external_target_baseline_verified')) {
    if ($manifest.$key -ne $true) { throw "Missing packaging check: $key" }
}
foreach ($key in @('vendor', 'odm', 'vbmeta')) {
    if ($manifest.baseline_sha256.$key -ne $baselines[$key]) { throw "Unexpected baseline: $key" }
}
$scope = @('bin/hw/dolbycodec2', 'bin/hw/vendor.dolby.media.c2@1.0-service', 'lib64/camera/aon_front.pb')
$expected = ($scope | Sort-Object) -join ','
if (($manifest.frozen_spec.partitions.PSObject.Properties.Name -join ',') -ne 'vendor' -or
    (($manifest.frozen_spec.partitions.vendor.files.PSObject.Properties.Name | Sort-Object) -join ',') -ne $expected -or
    (($manifest.partition_reports.vendor.changed_files | Sort-Object) -join ',') -ne $expected -or
    $manifest.partition_reports.vendor.metadata_preserved -ne $true) { throw 'Unexpected filesystem scope.' }
foreach ($relative in $scope) {
    if ($manifest.frozen_spec.partitions.vendor.files.$relative.sha256 -ne $build.reviewed_sha256.$relative) {
        throw "Unreviewed output: $relative"
    }
}
if (@($manifest.files).Count -ne 2 -or
    (($manifest.files.partition | Sort-Object) -join ',') -ne 'vbmeta,vendor') { throw 'Unexpected image set.' }
foreach ($file in $manifest.files) {
    $size = if ($file.partition -eq 'vendor') { 303517696 } else { 8192 }
    $path = Join-Path $images $file.name
    $item = Get-Item -LiteralPath $path -Force
    if ($file.name -ne ($file.partition + '.img') -or $file.bytes -ne $size -or $item.Length -ne $size -or
        ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
        throw "Image identity or hash mismatch: $($file.name)"
    }
}
Write-Output 'r23 vendor content, metadata, AON target and AVB parent verified.'
if (-not $Flash) { return }
$adb = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastboot = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$evidence = Join-Path $workspace ('reports/device/batch-r23-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $evidence | Out-Null
$log = Join-Path $evidence 'flash-and-reboot.txt'
function Invoke-DeviceTool([string]$tool, [string[]]$arguments) {
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $tool
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($argument in (@('-s', $serial) + $arguments)) { $start.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    if (-not $process.Start()) { throw 'Unable to launch device tool.' }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $timeout = if ($arguments[0] -eq 'flash') { 180000 } else { 30000 }
    if (-not $process.WaitForExit($timeout)) { $process.Kill(); throw 'Device tool timed out.' }
    $output = $stdout.Result + "`n" + $stderr.Result
    $exitCode = $process.ExitCode
    $process.Dispose()
    Add-Content -LiteralPath $log -Value $output -Encoding utf8
    if ($exitCode -ne 0) { throw $output }
    return $output
}
if ((Invoke-DeviceTool $adb @('shell', 'getprop ro.product.device')).Trim() -ne 'sheng' -or
    (Invoke-DeviceTool $adb @('shell', 'getprop ro.boot.slot_suffix')).Trim() -ne '_b' -or
    (Invoke-DeviceTool $adb @('shell', 'id -u')).Trim() -ne '0') { throw 'Wrong device, slot or root endpoint.' }
foreach ($partition in $baselines.Keys) {
    $command = if ($partition -in @('vbmeta', 'vbmeta_system')) {
        $bytes = if ($partition -eq 'vbmeta') { 8192 } else { 4096 }
        "dd if=/dev/block/by-name/${partition}_b bs=$bytes count=1 2>/dev/null | sha256sum"
    } else { "sha256sum /dev/block/mapper/${partition}_b" }
    $value = Invoke-DeviceTool $adb @('shell', $command)
    if ($value -notmatch ('(?m)^' + $baselines[$partition] + '\s')) { throw "Live baseline mismatch: $partition" }
}
Copy-Item -LiteralPath (Join-Path $images 'build-result.json') -Destination (Join-Path $evidence 'packaging-manifest.json')
Invoke-DeviceTool $adb @('reboot', 'fastboot') | Write-Output
$deadline = (Get-Date).AddSeconds(90)
$ready = $false
do {
    Start-Sleep -Seconds 3
    try { $ready = (Invoke-DeviceTool $fastboot @('getvar', 'is-userspace')) -match '(?m)^is-userspace:\s*yes\s*$' }
    catch { $ready = $false }
} until ($ready -or (Get-Date) -gt $deadline)
if (-not $ready) { throw 'Target fastbootd unavailable.' }
if ((Invoke-DeviceTool $fastboot @('getvar', 'product')) -notmatch '(?m)^product:\s*sheng\s*$' -or
    (Invoke-DeviceTool $fastboot @('getvar', 'current-slot')) -notmatch '(?m)^current-slot:\s*b\s*$') {
    throw 'Fastbootd identity mismatch.'
}
foreach ($partition in @('vendor', 'vbmeta')) {
    Invoke-DeviceTool $fastboot @('flash', ($partition + '_b'), (Join-Path $images ($partition + '.img'))) | Write-Output
}
Invoke-DeviceTool $fastboot @('reboot') | Write-Output
