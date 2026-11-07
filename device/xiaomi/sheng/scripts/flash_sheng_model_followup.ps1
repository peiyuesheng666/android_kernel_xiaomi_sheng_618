param([int]$Revision = 7)
# Flash the verified model-only system delta; keep reboot checks interactive.
$ErrorActionPreference = 'Stop'
if ($Revision -lt 7) { throw 'Model followups start at revision 7.' }
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$adbPath = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastbootPath = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$serial = 'ca10ede3'
$imageDirectory = Join-Path $workspace "artifacts/system-hardware-followup-sheng-r$Revision"
$manifest = Get-Content -LiteralPath (Join-Path $imageDirectory 'build-result.json') -Raw | ConvertFrom-Json
$requiredChecks = @(
    'baseline_descriptor_matches_installed_chain',
    'build_prop_inode_number_preserved', 'build_prop_allocated_blocks_preserved',
    'build_prop_mode_owner_group_times_and_all_xattrs_preserved',
    'all_other_files_and_inode_bytes_preserved', 'exact_system_base_verified',
    'filesystem_readback_verified', 'readonly_e2fsck_passed',
    'partition_sizes_unchanged', 'system_hashtree_verified', 'signatures_verified',
    'only_system_avb_descriptor_changed', 'other_avb_descriptors_and_header_preserved',
    'vendor_odm_and_vbmeta_untouched'
)
foreach ($check in $requiredChecks) {
    if ($manifest.$check -ne $true) { throw "Missing image verification: $check" }
}
if ($manifest.changed_property -ne 'ro.product.model' -or
        $manifest.model -ne 'Xiaomi Pad 6S Pro 12.4' -or
        @($manifest.changed_system_files).Count -ne 1 -or
        $manifest.changed_system_files[0] -ne '/system/build.prop') {
    throw 'Unexpected model-change scope.'
}
$expectedSystemBase = 'f89b07d973531ceea3d2d3a695754065382947b401393d382862f3b44a03aea4'
$expectedVbmetaSystemBase = 'cbc5326ebc2529cb108ff0673357c3fd6f3b44096ed42dbd00e0a7742833f06b'
$expectedR6Vendor = 'c663a57f003d3cd0791ec2a7b50ad36ed1e1d1d96c0b4b414adc5b3bc63ef038'
$expectedR6Vbmeta = '488757df791a7cdf9387e2b81b30fbddb2210a6a0ccdf338048dc8f0c75e33af'
if ($manifest.raw_base_sha256 -ne $expectedSystemBase -or
        $manifest.vbmeta_system_base_sha256 -ne $expectedVbmetaSystemBase) {
    throw 'Unexpected source-image baseline.'
}
$partitions = @('system', 'vbmeta_system')
if (@($manifest.files).Count -ne 2 -or
        (($manifest.files.partition | Sort-Object) -join ',') -ne (($partitions | Sort-Object) -join ',')) {
    throw 'Unexpected partition set.'
}
foreach ($file in $manifest.files) {
    $expectedBytes = if ($file.partition -eq 'system') { 1005133824L } else { 4096L }
    if ($file.name -ne ($file.partition + '.img') -or $file.bytes -ne $expectedBytes -or
            $file.sha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'Unexpected image identity or partition size.'
    }
    $image = Join-Path $imageDirectory $file.name
    if ((Get-Item -LiteralPath $image).Length -ne $file.bytes -or
            (Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
        throw "Image changed: $($file.name)"
    }
}
$evidenceDirectory = Join-Path $workspace ('reports/device/model-r' + $Revision + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $evidenceDirectory | Out-Null
$logPath = Join-Path $evidenceDirectory 'flash-and-reboot.txt'

function Invoke-SerialTool([string]$executable, [string[]]$arguments) {
    $result = & $executable -s $serial @arguments 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($result | ForEach-Object { $_.ToString() }) -join "`n"
    Add-Content -LiteralPath $logPath -Value $text -Encoding UTF8
    if ($exitCode -ne 0) { throw $text }
    return $text
}

function Assert-LiveHash([string]$name, [string]$command, [string]$expected) {
    $actual = Invoke-SerialTool $adbPath @('shell', $command)
    if ($actual -notmatch ('(?m)^' + $expected + '\s')) {
        throw "Installed $name does not match the verified base."
    }
}

$inventory = & $adbPath devices 2>&1
if ($LASTEXITCODE -ne 0 -or ($inventory -join "`n") -notmatch '(?m)^ca10ede3\s+device\s*$') {
    throw 'The authorized tablet ADB endpoint is unavailable.'
}
$product = Invoke-SerialTool $adbPath @('shell', 'getprop ro.product.device')
$slot = Invoke-SerialTool $adbPath @('shell', 'getprop ro.boot.slot_suffix')
$uid = Invoke-SerialTool $adbPath @('shell', 'id -u')
if ($product.Trim() -ne 'sheng' -or $slot.Trim() -ne '_b') { throw 'Device or active slot mismatch.' }
if ($uid.Trim() -ne '0') { throw 'Root ADB is required for the installed-image hash checks.' }
# Verify both the current model base and the r6 graphics/audio baseline before
# any reboot. Only the two images listed above are ever sent to Fastboot.
Assert-LiveHash 'r6 vendor_b' 'sha256sum /dev/block/by-name/vendor_b' $expectedR6Vendor
Assert-LiveHash 'r6 vbmeta_b prefix' 'dd if=/dev/block/by-name/vbmeta_b bs=8192 count=1 2>/dev/null | sha256sum' $expectedR6Vbmeta
Assert-LiveHash 'system_b' 'sha256sum /dev/block/by-name/system_b' $expectedSystemBase
Assert-LiveHash 'vbmeta_system_b prefix' 'dd if=/dev/block/by-name/vbmeta_system_b bs=4096 count=1 2>/dev/null | sha256sum' $expectedVbmetaSystemBase
Invoke-SerialTool $adbPath @('shell', 'getprop ro.product.model; getprop ro.product.system.model') |
    Set-Content -LiteralPath (Join-Path $evidenceDirectory 'before-model-properties.txt') -Encoding UTF8
Copy-Item -LiteralPath (Join-Path $imageDirectory 'build-result.json') -Destination (Join-Path $evidenceDirectory 'packaging-manifest.json')
Invoke-SerialTool $adbPath @('reboot', 'fastboot') | Write-Output
$deadline = (Get-Date).AddSeconds(90)
$ready = $false
do {
    Start-Sleep -Seconds 3
    try {
        # Inventory is nonblocking when disconnected; never issue getvar until
        # the exact serial is present during the USB transition.
        $devices = Invoke-SerialTool $fastbootPath @('devices')
        if ($devices -match '(?m)^ca10ede3\s+fastboot(?:\s|$)') {
            $userspace = Invoke-SerialTool $fastbootPath @('getvar', 'is-userspace')
            $ready = $userspace -match '(?m)^is-userspace:\s*yes\s*$'
        }
    } catch { $ready = $false }
} until ($ready -or (Get-Date) -gt $deadline)
if (-not $ready) { throw 'Fastbootd did not become ready.' }
$product = Invoke-SerialTool $fastbootPath @('getvar', 'product')
$slot = Invoke-SerialTool $fastbootPath @('getvar', 'current-slot')
if ($product -notmatch '(?m)^product:\s*sheng\s*$' -or $slot -notmatch '(?m)^current-slot:\s*b\s*$') {
    throw 'Fastbootd device or slot mismatch.'
}
foreach ($partition in $partitions) {
    Write-Output "Flashing ${partition}_b"
    Invoke-SerialTool $fastbootPath @('flash', ($partition + '_b'),
            (Join-Path $imageDirectory ($partition + '.img'))) | Write-Output
}
Invoke-SerialTool $fastbootPath @('reboot') | Write-Output
Write-Output "Model delta flash complete; reboot validation pending. Evidence: $evidenceDirectory"
