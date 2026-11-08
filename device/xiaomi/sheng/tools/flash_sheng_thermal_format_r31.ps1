param([switch]$Flash, [switch]$VerifyRuntime)
$ErrorActionPreference = 'Stop'
if ($Flash -and $VerifyRuntime) { throw 'Select a single operation.' }
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$images = Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r31'
$serial = 'ca10ede3'
$baseline = @{
    system = '0f9c8ad6341faae4abaa9c080614d6d879aa62e85e36383086bb0333adfb4dce'
    system_ext = 'ccda96e9d2590f4aebf8327e9d2fa1f21ec4358cdd4d78add1557d3d0443263c'
    odm = 'eecbef1b87f4055f5c35c519d2d1d220b479e0fe6320d970708e277ebba532c0'
    vendor = 'b0e5ff1c8b259a66a7e2907ee6d22121cd1094a6ecc4c82e467decab25462184'
    vendor_dlkm = '94ab3296f0a23c2337fd40e641839e69384cd14e7f83ae76cdfa4ae132d30859'
    vbmeta = 'f9fe4bdd11d692d3c5427aacb89532c7959691d70509ace9905fc13c8075b440'
    vbmeta_system = '7f3c4603e9fc7fedd923b074c9086c2d3520d7b375add56bbbb3d32f7a07411c'
}
$manifestPath = Join-Path $images 'build-result.json'
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.revision -ne 31 -or $manifest.frozen_spec.revision -ne 31) { throw 'Wrong revision.' }
foreach ($key in @('exact_baselines_verified', 'all_filesystem_stages_verified',
    'root_signature_verified', 'root_other_descriptors_unchanged',
    'original_systemui_required', 'system_ext_and_vbmeta_system_unchanged')) {
    if ($manifest.$key -ne $true) { throw "Missing packaging review: $key" }
}
$specPath = Join-Path $workspace 'device/xiaomi/sheng/docs/batch-r31-inputs-20261108.json'
if ((Get-FileHash -LiteralPath $specPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.spec_sha256) {
    throw 'Frozen specification changed.'
}
foreach ($entry in $manifest.frozen_spec.reviews_sha256.PSObject.Properties) {
    $path = Join-Path $workspace ('device/xiaomi/sheng/' + $entry.Name)
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw "Review changed: $($entry.Name)"
    }
}
$reviewPath = Join-Path $workspace 'device/xiaomi/sheng/docs/r31-thermal-format-build-review-20261108.json'
$review = Get-Content -Raw -LiteralPath $reviewPath | ConvertFrom-Json
foreach ($key in @('scoped_configuration_assembly_passed','property_info_checker_passed',
    'original_library_elf_check_passed','diagnostic_native_build_passed',
    'postbuild_public_audit_passed','target_original_library_probe_passed')) {
    if ($review.$key -ne $true) { throw "Missing build/probe review: $key" }
}
if ($review.full_product_build_passed -ne $false) { throw 'Do not claim a full product build.' }
foreach ($entry in $manifest.frozen_spec.device_inputs.PSObject.Properties) {
    $path = Join-Path $workspace ('device/xiaomi/sheng/' + $entry.Name)
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw "Device input changed: $($entry.Name)"
    }
}
$scope = @{vendor=@('etc/selinux/vendor_property_contexts','lib64/libcamxexternalformatutils.so')}
if ((($manifest.frozen_spec.partitions.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'vendor') {
    throw 'Unexpected partition scope.'
}
foreach ($partition in $scope.Keys) {
    if ($manifest.baseline_sha256.$partition -ne $baseline[$partition] -or
        $manifest.frozen_spec.baseline_sha256.$partition -ne $baseline[$partition]) { throw 'Wrong baseline.' }
    $stage = $manifest.frozen_spec.partitions.$partition
    $report = $manifest.partition_reports.$partition
    $expected = ($scope[$partition] | Sort-Object) -join ','
    if ((($stage.files.PSObject.Properties.Name | Sort-Object) -join ',') -ne $expected -or
        (($report.changed_files | Sort-Object) -join ',') -ne $expected -or
        $report.metadata_preserved -ne $true) {
        throw "Unexpected filesystem scope: $partition"
    }
    if ((($stage.new_nodes.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'lib64/libcamxexternalformatutils.so') {
        throw 'Only the original missing camera-format library may be a new node.'
    }
    $node = $stage.new_nodes.'lib64/libcamxexternalformatutils.so'
    if ($node.uid -ne 0 -or $node.gid -ne 0 -or ($node.mode -band 511) -ne 420 -or
        $node.selinux -ne 'u:object_r:vendor_file:s0') { throw 'Incorrect new library metadata.' }
    if ($stage.files.'lib64/libcamxexternalformatutils.so'.sha256 -ne
        '7a1affdcba4a1dc835e5ac1944bbea864056fb38bec45c87538ef4df9a2be599' -or
        $stage.files.'etc/selinux/vendor_property_contexts'.sha256 -ne
        'f07db61960d8aa6e0a09207f0910c080af407ad36d1584d358e423f32156903f') {
        throw 'The two reviewed vendor payloads changed.'
    }
}
if ($manifest.baseline_sha256.vbmeta -ne $baseline.vbmeta) { throw 'Wrong AVB root.' }
$sizes = @{vendor=303517696; vbmeta=8192}
if (@($manifest.files).Count -ne 2 -or (($manifest.files.partition | Sort-Object) -join ',') -ne 'vbmeta,vendor') {
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
Write-Output 'r31 reviewed inputs, exact file scope, image hashes and AVB checks passed.'
if (-not $Flash -and -not $VerifyRuntime) { return }
$adb = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastboot = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$evidence = Join-Path $workspace ('reports/device/r31-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
    if ((Invoke-Target $adb @('shell','stat -c "%u %g %a" /vendor/lib64/libcamxexternalformatutils.so')).Trim() -ne '0 0 644' -or
        (Invoke-Target $adb @('shell','ls -Zd /vendor/lib64/libcamxexternalformatutils.so')) -notmatch
        'u:object_r:vendor_file:s0') { throw 'Installed library metadata differs.' }
    Invoke-Target $adb @('shell','getprop sys.boot_completed; getenforce; settings get secure adaptive_sleep; settings get system screen_off_timeout; getprop init.svc.mi_thermald; getprop init.svc.vendor.thermal-hal; cat /sys/class/thermal/thermal_message/sconfig; pidof com.android.systemui; pidof vendor.qti.camera.provider-service_64') | Write-Output
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
foreach ($p in @('vendor','vbmeta')) {
    Invoke-Target $fastboot @('flash',($p + '_b'),(Join-Path $images ($p + '.img'))) | Write-Output
}
Invoke-Target $fastboot @('reboot') | Write-Output
Write-Output "r31 written to ca10ede3 / b; evidence: $evidence"
