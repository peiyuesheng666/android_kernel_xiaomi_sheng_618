param([switch]$Flash)
$ErrorActionPreference = 'Stop'
if ($Flash) { throw 'r24 SystemUI replacement was withdrawn: the user forbids modifying SystemUI.' }
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$images = Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r24'
$serial = 'ca10ede3'
$baselines = @{
    system = '0f9c8ad6341faae4abaa9c080614d6d879aa62e85e36383086bb0333adfb4dce'
    system_ext = '82006f12228ebda0a521a96f8373c48bb52edb981a790830304f8ea50aa60419'
    odm = 'c315f3e80f292909740d3e052102dcabb36b3f3bcaa817918f9dbc92630ce651'
    vendor = '49205891b29be48360a717733200a94d8179f4615cf98008b5094fc5e46a481e'
    vbmeta = 'c6a46fc8589e5fefb5f84bcc5eb0bae724df03d35c0b016c7ac986e5474804d3'
    vbmeta_system = '3fe3413cc7fe8786372606ebfe7f9470e41bbf34b1dbcb5db7397540d9afc26a'
}
$manifest = Get-Content -Raw -LiteralPath (Join-Path $images 'build-result.json') | ConvertFrom-Json
$build = Get-Content -Raw -LiteralPath (Join-Path $workspace 'device/xiaomi/sheng/docs/build-r24-video-power-20261108.json') | ConvertFrom-Json
if ($manifest.revision -ne 24 -or $manifest.frozen_spec.revision -ne 24) { throw 'Wrong batch revision.' }
foreach ($key in @('build_passed', 'helper_tests_passed', 'upstream_audit_passed',
    'geometry_tests_passed', 'apk_transform_verified')) {
    if ($build.$key -ne $true) { throw "Missing build review: $key" }
}
foreach ($key in @('exact_baselines_verified', 'all_filesystem_stages_verified', 'both_parent_chains_verified')) {
    if ($manifest.$key -ne $true) { throw "Missing packaging check: $key" }
}
foreach ($key in @('vendor', 'system_ext', 'vbmeta', 'vbmeta_system', 'system')) {
    if ($manifest.baseline_sha256.$key -ne $baselines[$key]) { throw "Unexpected baseline: $key" }
}
$scope = @{
    vendor = @('lib64/c2.dolby.hevc.dec.so', 'lib64/c2.dolby.hevc.sec.dec.so')
    system_ext = @('priv-app/SystemUI/SystemUI.apk')
}
if ((($manifest.frozen_spec.partitions.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'system_ext,vendor') {
    throw 'Unexpected partition scope.'
}
foreach ($partition in $scope.Keys) {
    $stage = $manifest.frozen_spec.partitions.$partition
    $report = $manifest.partition_reports.$partition
    $expected = ($scope[$partition] | Sort-Object) -join ','
    if ((($stage.files.PSObject.Properties.Name | Sort-Object) -join ',') -ne $expected -or
        (($report.changed_files | Sort-Object) -join ',') -ne $expected -or
        @($stage.new_nodes.PSObject.Properties).Count -ne 0 -or $report.metadata_preserved -ne $true) {
        throw "Unexpected filesystem scope or metadata: $partition"
    }
    foreach ($relative in $scope[$partition]) {
        if ($stage.files.$relative.sha256 -ne $build.reviewed_sha256.$partition.$relative) {
            throw "Unreviewed output: $partition/$relative"
        }
    }
}
if ($manifest.frozen_spec.installed_sources.system_ext.'priv-app/SystemUI/SystemUI.apk' -ne
    'priv-app/ShengSystemUI/SystemUI.apk') { throw 'Wrong installed APK mapping.' }
$reviewPath = Join-Path $workspace 'device/xiaomi/sheng/docs/build-r24-video-power-20261108.json'
if ((Get-FileHash -LiteralPath $reviewPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    $manifest.frozen_spec.build_review_sha256) { throw 'Build review changed.' }
$sizes = @{vendor=303517696; system_ext=572813312; vbmeta=8192; vbmeta_system=4096}
if (@($manifest.files).Count -ne 4 -or
    (($manifest.files.partition | Sort-Object) -join ',') -ne 'system_ext,vbmeta,vbmeta_system,vendor') {
    throw 'Unexpected image set.'
}
foreach ($file in $manifest.files) {
    $path = Join-Path $images $file.name
    $item = Get-Item -LiteralPath $path -Force
    if ($file.name -ne ($file.partition + '.img') -or $file.bytes -ne $sizes[$file.partition] -or
        $item.Length -ne $file.bytes -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
        throw "Image identity or hash mismatch: $($file.name)"
    }
}
Write-Output 'r24 video libraries, SystemUI, metadata and both AVB parents verified.'
if (-not $Flash) { return }
$adb = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastboot = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$evidence = Join-Path $workspace ('reports/device/batch-r24-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
foreach ($partition in @('vendor', 'system_ext', 'vbmeta', 'vbmeta_system')) {
    Invoke-DeviceTool $fastboot @('flash', ($partition + '_b'), (Join-Path $images ($partition + '.img'))) | Write-Output
}
Invoke-DeviceTool $fastboot @('reboot') | Write-Output
