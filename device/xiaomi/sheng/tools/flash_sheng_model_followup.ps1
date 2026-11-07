param([int]$Revision = 20, [switch]$Flash)
# Verify the exact identity delta by default; -Flash applies it to slot b.
$ErrorActionPreference = 'Stop'
if ($Revision -notin @(7,20)) { throw 'Only the exact r7 or r20 identity profiles are supported.' }
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
$targetModel = if ($Revision -eq 20) { '24018RPACC' } else { 'Xiaomi Pad 6S Pro 12.4' }
if ($manifest.changed_property -ne 'ro.product.model' -or
        $manifest.model -ne $targetModel -or
        @($manifest.changed_system_files).Count -ne 1 -or
        $manifest.changed_system_files[0] -ne '/system/build.prop') {
    throw 'Unexpected model-change scope.'
}
if ($Revision -eq 20 -and ($manifest.revision -ne 20 -or
        $manifest.marketname -ne 'Xiaomi Pad 6S Pro 12.4' -or
        (($manifest.changed_properties | Sort-Object) -join ',') -ne 'ro.product.marketname,ro.product.model')) {
    throw 'The hardware-model/marketname correction is missing.'
}
$expectedSystemBase = 'f89b07d973531ceea3d2d3a695754065382947b401393d382862f3b44a03aea4'
$expectedVbmetaSystemBase = 'cbc5326ebc2529cb108ff0673357c3fd6f3b44096ed42dbd00e0a7742833f06b'
$expectedVendor = 'c663a57f003d3cd0791ec2a7b50ad36ed1e1d1d96c0b4b414adc5b3bc63ef038'
$expectedVbmeta = '488757df791a7cdf9387e2b81b30fbddb2210a6a0ccdf338048dc8f0c75e33af'
if ($Revision -eq 20) {
    $expectedSystemBase = '0551a74f4f995793665a485d10caacffb22ccd8fdaffb78d7811d17c658b3ac1'
    $expectedVbmetaSystemBase = '666176dacf6756e069e1779d27275a0a6c8e1a4d7ba7648f40d0327aa940d44d'
    $expectedVendor = '140df691149b4b731caf2dca730de4403b6cf45bb1e7a004a1dbc228b1d4c8b5'
    $expectedVbmeta = 'd31c33d7a479cb621e7b25e97afaf5636de3eea64e0c75a294420f313ffe9ba5'
}
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
Write-Output "r$Revision identity images and AVB chain verified."
if (-not $Flash) { return }

$evidenceDirectory = Join-Path $workspace ('reports/device/model-r' + $Revision + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $evidenceDirectory | Out-Null
$logPath = Join-Path $evidenceDirectory 'flash-and-reboot.txt'

function Invoke-SerialTool([string]$executable, [string[]]$arguments) {
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $executable
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $allArguments = @('-s', $serial) + $arguments
    if ($null -ne $startInfo.ArgumentList) {
        foreach ($argument in $allArguments) { $startInfo.ArgumentList.Add($argument) }
    } else {
        $quotedArguments = foreach ($argument in $allArguments) {
            if ($argument -match '[\s"]' -or $argument.Length -eq 0) {
                $quoted = [regex]::Replace($argument, '(\\*)"', '$1$1\"')
                $quoted = [regex]::Replace($quoted, '(\\+)$', '$1$1')
                '"' + $quoted + '"'
            } else { $argument }
        }
        $startInfo.Arguments = $quotedArguments -join ' '
    }
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    if (-not $process.Start()) { throw 'Unable to launch USB tool.' }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $timeout = if ($arguments[0] -eq 'flash') { 180000 } else { 30000 }
    if (-not $process.WaitForExit($timeout)) {
        $process.Kill()
        $process.WaitForExit()
        Add-Content -LiteralPath $logPath -Value ($stdout.Result + "`n" + $stderr.Result) -Encoding UTF8
        $process.Dispose()
        throw "USB tool timed out: $($arguments[0])"
    }
    $exitCode = $process.ExitCode
    $output = $stdout.Result + "`n" + $stderr.Result
    $process.Dispose()
    Add-Content -LiteralPath $logPath -Value $output -Encoding UTF8
    if ($exitCode -ne 0) { throw $output }
    return $output
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
# Verify the exact installed identity and graphics/audio baseline before
# any reboot. Only the two images listed above are ever sent to Fastboot.
Assert-LiveHash 'vendor_b' 'sha256sum /dev/block/mapper/vendor_b' $expectedVendor
Assert-LiveHash 'vbmeta_b prefix' 'dd if=/dev/block/by-name/vbmeta_b bs=8192 count=1 2>/dev/null | sha256sum' $expectedVbmeta
if ($Revision -eq 20) {
    Assert-LiveHash 'system_ext_b' 'sha256sum /dev/block/mapper/system_ext_b' '9663016b59a90b30cb573dd45785f01ef1ef0ccefad6572279051cdec92a220a'
    Assert-LiveHash 'odm_b' 'sha256sum /dev/block/mapper/odm_b' '405d4004558bf5caea30874f301780d2a180c2da0ecc1ba143f7bdaa3ac1dfcf'
}
Assert-LiveHash 'system_b' 'sha256sum /dev/block/mapper/system_b' $expectedSystemBase
Assert-LiveHash 'vbmeta_system_b prefix' 'dd if=/dev/block/by-name/vbmeta_system_b bs=4096 count=1 2>/dev/null | sha256sum' $expectedVbmetaSystemBase
Invoke-SerialTool $adbPath @('shell', 'getprop ro.product.model; getprop ro.product.marketname; getprop ro.product.system.model; getprop ro.build.characteristics') |
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
