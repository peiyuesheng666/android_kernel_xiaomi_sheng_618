param([switch]$Flash, [switch]$VerifyRuntime)
$ErrorActionPreference = 'Stop'
if ($Flash -and $VerifyRuntime) { throw 'Select a single operation.' }
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$images = Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r32'
$serial = 'ca10ede3'
$baseline = @{
    system = '0f9c8ad6341faae4abaa9c080614d6d879aa62e85e36383086bb0333adfb4dce'
    system_ext = 'ccda96e9d2590f4aebf8327e9d2fa1f21ec4358cdd4d78add1557d3d0443263c'
    odm = 'eecbef1b87f4055f5c35c519d2d1d220b479e0fe6320d970708e277ebba532c0'
    vendor = '033fdfcc1100e8d504739c43442a6b4e57e73088b938d2f9a9bff9369702217f'
    vendor_dlkm = '94ab3296f0a23c2337fd40e641839e69384cd14e7f83ae76cdfa4ae132d30859'
    vbmeta = 'f6ba37f234fcdacbd36b7837e1d6f6a3ecd6cb147269291548089e626fb9a834'
    vbmeta_system = '7f3c4603e9fc7fedd923b074c9086c2d3520d7b375add56bbbb3d32f7a07411c'
}
$manifestPath = Join-Path $images 'build-result.json'
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.revision -ne 32 -or $manifest.frozen_spec.revision -ne 32) { throw 'Wrong revision.' }
foreach ($key in @('exact_baselines_verified', 'all_filesystem_stages_verified',
    'both_parent_chains_verified', 'both_parent_signatures_verified', 'other_avb_descriptors_unchanged',
    'original_systemui_required', 'system_ext_and_vendor_dlkm_unchanged')) {
    if ($manifest.$key -ne $true) { throw "Missing packaging review: $key" }
}
$specPath = Join-Path $workspace 'device/xiaomi/sheng/docs/batch-r32-growth-inputs-20261108.json'
if ((Get-FileHash -LiteralPath $specPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.spec_sha256) {
    throw 'Frozen specification changed.'
}
foreach ($entry in $manifest.frozen_spec.reviews_sha256.PSObject.Properties) {
    $path = Join-Path $workspace ('device/xiaomi/sheng/' + $entry.Name)
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw "Review changed: $($entry.Name)"
    }
}
$reviewPath = Join-Path $workspace 'device/xiaomi/sheng/docs/r32-face-growth-build-review-20261108.json'
$review = Get-Content -Raw -LiteralPath $reviewPath | ConvertFrom-Json
foreach ($key in @('scoped_configuration_assembly_passed','baseline_matrix_byte_reproduced',
    'only_miface_matrix_hal_added','complete_live_vintf_compatibility_passed',
    'actual_kernel_config_checked','exact_face_context_and_policy_checks_passed','postbuild_public_audit_passed',
    'normal_strip_rule_reused','all_runtime_elf_sections_preserved','five_stripped_candidate_elf_checks_passed',
    'vendor_reserve_configuration_checked','live_super_space_checked')) {
    if ($review.$key -ne $true) { throw "Missing build review: $key" }
}
if ($review.full_product_build_passed -ne $false) { throw 'Do not claim a full product build.' }
foreach ($entry in $manifest.frozen_spec.device_inputs.PSObject.Properties) {
    $path = Join-Path $workspace ('device/xiaomi/sheng/' + $entry.Name)
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw "Device input changed: $($entry.Name)"
    }
}
$scope = @{
    system = @('etc/vintf/compatibility_matrix.device.xml')
    vendor = @('lib64/android.hardware.biometrics.common-V2-ndk.so','lib64/android.hardware.biometrics.face-V2-ndk.so',
        'etc/permissions/android.hardware.biometrics.face.xml','etc/selinux/vendor_sepolicy.cil',
        'etc/selinux/vendor_file_contexts','etc/selinux/vendor_hwservice_contexts')
    odm = @('bin/hw/android.hardware.biometrics.face-aidl-service','bin/mifaced@1.0',
        'etc/init/android.hardware.biometrics.face-aidl-service.rc','etc/init/vendor.xiaomi.hardware.miface@1.0-service.rc',
        'etc/vintf/manifest/face-default.xml','etc/vintf/manifest/manifest_vendor.xiaomi.hardware.miface.xml',
        'etc/selinux/precompiled_sepolicy')
}
if ((($manifest.frozen_spec.partitions.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'odm,system,vendor') {
    throw 'Unexpected partition scope.'
}
foreach ($partition in $scope.Keys) {
    if ($manifest.baseline_sha256.$partition -ne $baseline[$partition] -or
        $manifest.frozen_spec.baseline_sha256.$partition -ne $baseline[$partition]) { throw 'Wrong baseline.' }
    $stage = $manifest.frozen_spec.partitions.$partition
    $report = $manifest.partition_reports.$partition
    $expectedFiles = ($scope[$partition] | Sort-Object) -join ','
    $expectedChanged = if ($partition -eq 'system') {'system/etc/vintf/compatibility_matrix.device.xml'} else {$expectedFiles}
    if ((($stage.files.PSObject.Properties.Name | Sort-Object) -join ',') -ne $expectedFiles -or
        (($report.changed_files | Sort-Object) -join ',') -ne $expectedChanged -or $report.metadata_preserved -ne $true) {
        throw "Unexpected filesystem scope: $partition"
    }
    foreach ($entry in $stage.files.PSObject.Properties) {
        if ($entry.Value.sha256 -ne $review.reviewed_sha256.$partition.($entry.Name)) { throw 'Payload review mismatch.' }
    }
    $expectedNodes = switch ($partition) {
        'system' { @() }
        'vendor' { @($scope.vendor | Where-Object { -not $_.StartsWith('etc/selinux/') }) }
        'odm' { @($scope.odm | Where-Object { $_ -ne 'etc/selinux/precompiled_sepolicy' }) }
    }
    if ((($stage.new_nodes.PSObject.Properties.Name | Sort-Object) -join ',') -ne (($expectedNodes | Sort-Object) -join ',')) {
        throw 'Unexpected new node set.'
    }
    foreach ($entry in $stage.new_nodes.PSObject.Properties) {
        $node = $entry.Value
        $mode = if ($entry.Name.StartsWith('bin/')) {493} else {420}
        $label = if ($entry.Name.StartsWith('bin/hw/')) {'hal_face_default_exec'} elseif ($entry.Name.StartsWith('bin/')) {
            'hal_miface_default_exec'
        } elseif ($entry.Name.StartsWith('lib64/')) {'vendor_file'} else {'vendor_configs_file'}
        if ($node.uid -ne 0 -or $node.gid -ne 0 -or $node.mode -ne $mode -or $node.selinux -ne "u:object_r:${label}:s0") {
            throw 'Incorrect new node metadata.'
        }
    }
}
foreach ($p in @('vbmeta','vbmeta_system')) {
    if ($manifest.baseline_sha256.$p -ne $baseline[$p] -or $manifest.frozen_spec.baseline_sha256.$p -ne $baseline[$p]) {
        throw 'Wrong AVB parent baseline.'
    }
}
$sizes = @{system=1005133824; vendor=352321536; odm=1141067776; vbmeta=8192; vbmeta_system=4096}
if ($manifest.vendor_logical_partition_growth.before -ne 303517696 -or
    $manifest.vendor_logical_partition_growth.after -ne $sizes.vendor -or
    $manifest.vendor_logical_partition_growth.required_payload_reserve -ne 33554432 -or
    $manifest.partition_reports.vendor.free_payload_bytes -lt 33554432) { throw 'Unreviewed vendor growth.' }
if (@($manifest.files).Count -ne 5 -or (($manifest.files.partition | Sort-Object) -join ',') -ne 'odm,system,vbmeta,vbmeta_system,vendor') {
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
Write-Output 'r32 reviewed inputs, exact file scope, image hashes and AVB checks passed.'
if (-not $Flash -and -not $VerifyRuntime) { return }
$adb = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastboot = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$evidence = Join-Path $workspace ('reports/device/r32-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
    foreach ($p in $scope.Keys) {
        foreach ($entry in $manifest.frozen_spec.partitions.$p.new_nodes.PSObject.Properties) {
            $node = $entry.Value
            $path = '/' + $p + '/' + $entry.Name
            $expectedStat = '0 0 ' + [Convert]::ToString([int]$node.mode, 8)
            if ((Invoke-Target $adb @('shell',('stat -c "%u %g %a" ' + $path))).Trim() -ne $expectedStat -or
                (Invoke-Target $adb @('shell',('ls -Zd ' + $path))) -notmatch [regex]::Escape($node.selinux)) {
                throw "Installed metadata mismatch: $path"
            }
        }
    }
    Invoke-Target $adb @('shell','getprop sys.boot_completed; getenforce; settings get secure adaptive_sleep; settings get system screen_off_timeout; getprop init.svc.mi_thermald; getprop init.svc.vendor.thermal-hal; cat /sys/class/thermal/thermal_message/sconfig; pidof com.android.systemui; pidof vendor.qti.camera.provider-service_64') | Write-Output
    Write-Output "Seven partition/file hashes verified; evidence: $evidence"
    return
}
$layout = Invoke-Target $adb @('shell','lpdump --slot=1 /dev/block/by-name/super')
Set-Content -LiteralPath (Join-Path $evidence 'super-before-resize.txt') -Value $layout -Encoding utf8
if ($layout -notmatch 'Update state:\s*none' -or $layout -notmatch 'Using snapuserd:\s*0' -or
    $layout -notmatch 'Current slot:\s*_b' -or $layout -notmatch 'Name:\s*qti_dynamic_partitions_b\s+Maximum size:\s*(\d+) bytes') {
    throw 'Unexpected snapshot, slot or dynamic partition group.'
}
$groupMaximum = [long]$Matches[1]
$partitionTable = ($layout -split 'Super partition layout:')[0]
$sectors = [long]0
foreach ($extent in [regex]::Matches($partitionTable,'(?m)^\s+(\d+) \.\. (\d+) linear super \d+\s*$')) {
    $sectors += [long]$extent.Groups[2].Value - [long]$extent.Groups[1].Value + 1
}
if ($sectors -le 0 -or $groupMaximum - $sectors * 512 -lt ($sizes.vendor - 303517696 + 33554432)) {
    throw 'Insufficient checked group space for vendor growth.'
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
Invoke-Target $fastboot @('resize-logical-partition','vendor_b',[string]$sizes.vendor) | Write-Output
$vendorSize = Invoke-Target $fastboot @('getvar','partition-size:vendor_b')
if ($vendorSize -notmatch 'partition-size:vendor_b:\s*(0x[0-9a-fA-F]+)' -or
    [Convert]::ToInt64($Matches[1].Substring(2),16) -ne $sizes.vendor) { throw 'Vendor resize size mismatch.' }
foreach ($p in @('system','vendor','odm','vbmeta_system','vbmeta')) {
    Invoke-Target $fastboot @('flash',($p + '_b'),(Join-Path $images ($p + '.img'))) | Write-Output
}
Invoke-Target $fastboot @('reboot') | Write-Output
Write-Output "r32 written to ca10ede3 / b; evidence: $evidence"
