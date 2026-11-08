param([switch]$Flash)
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$images = Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r25'
$serial = 'ca10ede3'
$baselines = @{
    system = '0f9c8ad6341faae4abaa9c080614d6d879aa62e85e36383086bb0333adfb4dce'
    system_ext = '82006f12228ebda0a521a96f8373c48bb52edb981a790830304f8ea50aa60419'
    odm = 'c315f3e80f292909740d3e052102dcabb36b3f3bcaa817918f9dbc92630ce651'
    vendor = '4aa0518217ad9521d044b7408348039eb88457fa855bc3544cb499fea0299026'
    vbmeta = '883ba3ee6d22460c8a14f5a0eb04aabb4544d1d48d2386de52715b16ca7a9493'
    vbmeta_system = '3fe3413cc7fe8786372606ebfe7f9470e41bbf34b1dbcb5db7397540d9afc26a'
}
$chainPath = Join-Path $workspace 'device/xiaomi/sheng/docs/r25-restored-chain-20261108.json'
$chain = Get-Content -Raw -LiteralPath $chainPath | ConvertFrom-Json
foreach ($key in @('supplemental_chain_review_passed', 'sealed_r25_images_unchanged',
    'original_systemui_required', 'root_other_descriptors_unchanged', 'changed_child_descriptors_match',
    'accepted_system_parent_signature_verified', 'accepted_system_parent_key_matches_root',
    'system_descriptor_unchanged', 'system_ext_descriptor_matches_accepted_image')) {
    if ($chain.$key -ne $true) { throw "Missing restored-chain review: $key" }
}
$manifestPath = Join-Path $images 'build-result.json'
if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    $chain.manifest_sha256) { throw 'Sealed r25 manifest changed after supplemental review.' }
$manifest = Get-Content -Raw -LiteralPath (Join-Path $images 'build-result.json') | ConvertFrom-Json
$reviewPath = Join-Path $workspace 'device/xiaomi/sheng/docs/build-r25-graphicbuffer-20261108.json'
$build = Get-Content -Raw -LiteralPath $reviewPath | ConvertFrom-Json
if ($manifest.revision -ne 25 -or $manifest.frozen_spec.revision -ne 25) { throw 'Wrong batch revision.' }
foreach ($key in @('build_passed', 'helper_tests_passed', 'upstream_audit_passed',
    'layout_archive_verified', 'allocation_instructions_verified')) {
    if ($build.$key -ne $true) { throw "Missing build review: $key" }
}
if ($build.allocation_sites -ne 14 -or $build.graphic_buffer_bytes -ne 3376 -or
    $build.malformed_input_checks_passed -ne 5) { throw 'Wrong layout or transform coverage.' }
foreach ($key in @('exact_baselines_verified', 'all_filesystem_stages_verified',
    'both_changed_child_descriptors_verified')) {
    if ($manifest.$key -ne $true) { throw "Missing packaging check: $key" }
}
foreach ($key in @('odm', 'vendor', 'vbmeta')) {
    if ($manifest.baseline_sha256.$key -ne $baselines[$key]) { throw "Unexpected baseline: $key" }
}
$scope = @{
    odm = @('lib64/hw/camera.xiaomi.so', 'lib64/libcom.xiaomi.grallocutils.so',
        'lib64/libcom.xiaomi.mawutils.so', 'lib64/libmis_plugin_vidhance.so')
    vendor = @('lib64/c2.dolby.hevc.dec.so', 'lib64/c2.dolby.hevc.enc.so', 'lib64/c2.dolby.hevc.sec.dec.so')
}
if ((($manifest.frozen_spec.partitions.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'odm,vendor') {
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
        if ($report.baseline_entries.$relative[0] -ne 'file' -or
            $report.baseline_entries.$relative[1] -ne $build.original_sha256.$partition.$relative) {
            throw "Unreviewed original file: $partition/$relative"
        }
    }
}
if ((Get-FileHash -LiteralPath $reviewPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    $manifest.frozen_spec.build_review_sha256) { throw 'Build review changed.' }
$specPath = Join-Path $workspace 'device/xiaomi/sheng/docs/batch-r25-inputs-20261108.json'
if ((Get-FileHash -LiteralPath $specPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne
    $manifest.spec_sha256) { throw 'Frozen specification changed.' }
$sizes = @{odm=1141067776; vendor=303517696; vbmeta=8192}
if (@($manifest.files).Count -ne 3 -or
    (($manifest.files.partition | Sort-Object) -join ',') -ne 'odm,vbmeta,vendor') { throw 'Unexpected image set.' }
foreach ($file in $manifest.files) {
    $path = Join-Path $images $file.name
    $item = Get-Item -LiteralPath $path -Force
    if ($file.name -ne ($file.partition + '.img') -or $file.bytes -ne $sizes[$file.partition] -or
        $file.sha256 -ne $chain.image_sha256.($file.partition) -or
        $item.Length -ne $file.bytes -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
        throw "Image identity or hash mismatch: $($file.name)"
    }
}
Write-Output 'r25 seven-library scope, metadata and both changed AVB children verified.'
if (-not $Flash) { return }
$adb = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastboot = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$evidence = Join-Path $workspace ('reports/device/batch-r25-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
    (Invoke-DeviceTool $adb @('shell', 'getprop sys.boot_completed')).Trim() -ne '1' -or
    (Invoke-DeviceTool $adb @('shell', 'id -u')).Trim() -ne '0') {
    throw 'Wrong device, slot, incomplete boot or non-root endpoint. This tool never runs adb root.'
}
foreach ($partition in $baselines.Keys) {
    $command = if ($partition -in @('vbmeta', 'vbmeta_system')) {
        $bytes = if ($partition -eq 'vbmeta') { 8192 } else { 4096 }
        "dd if=/dev/block/by-name/${partition}_b bs=$bytes count=1 2>/dev/null | sha256sum"
    } else { "sha256sum /dev/block/mapper/${partition}_b" }
    $value = Invoke-DeviceTool $adb @('shell', $command)
    if ($value -notmatch ('(?m)^' + $baselines[$partition] + '\s')) { throw "Live baseline mismatch: $partition" }
}
$systemui = Invoke-DeviceTool $adb @('shell', 'sha256sum /system_ext/priv-app/SystemUI/SystemUI.apk')
if ($systemui -notmatch '(?m)^33017b0d59e28da5db3e089a98f49601de508228a012392ee2d04c82cda3ccb1\s') {
    throw 'Original SystemUI must be preserved.'
}
Copy-Item -LiteralPath (Join-Path $images 'build-result.json') -Destination (Join-Path $evidence 'packaging-manifest.json')
Copy-Item -LiteralPath $chainPath -Destination (Join-Path $evidence 'restored-chain-review.json')
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
foreach ($partition in @('odm', 'vendor', 'vbmeta')) {
    Invoke-DeviceTool $fastboot @('flash', ($partition + '_b'), (Join-Path $images ($partition + '.img'))) | Write-Output
}
Invoke-DeviceTool $fastboot @('reboot') | Write-Output
