param([int]$Revision = 11)
# Flash only the selected revision's verified overlay/configuration partitions.
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$adbPath = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastbootPath = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$serial = 'ca10ede3'
$baselines = @{
    10 = @{
        OdmSha = '9735c4f6aa8dcc1f3b327b54ebc47f16b4c697e26095f7530d4671dfda3aac4d'
        VbmetaSha = '488757df791a7cdf9387e2b81b30fbddb2210a6a0ccdf338048dc8f0c75e33af'
        ChangedFiles = @('overlay/FrameworkResOverlaySheng.apk', 'overlay/SystemUIResOverlaySheng.apk')
    }
    11 = @{
        OdmSha = '35ceeb371eedb76f4d268ae5a65387f2353150e6b86a84366039821aa69b4d0c'
        VbmetaSha = '5e3c933a430680a1b150607580c2f711166992b6c0fb9520a8c5ecc6edf0f312'
        ChangedFiles = @('overlay/SystemUIResOverlaySheng.apk')
    }
    12 = @{
        OdmSha = 'd947ae93faad87bcb26da93afe245d6528e04f2b698ca4116257d29262ff5aac'
        VbmetaSha = '43412dea1eebb58489cd8acfec9368123af94090d3b2665aab225abc61f17e78'
        ChangedFiles = @('overlay/FrameworkResOverlaySheng.apk')
    }
}
if (-not $baselines.ContainsKey($Revision)) { throw 'No verified baseline for this revision.' }
$baseline = $baselines[$Revision]
$imageDirectory = Join-Path $workspace "artifacts/system-hardware-followup-sheng-r$Revision"
$manifest = Get-Content -LiteralPath (Join-Path $imageDirectory 'build-result.json') -Raw | ConvertFrom-Json
if ($manifest.revision -ne $Revision) { throw 'Overlay manifest revision mismatch.' }
$checks = @(
    'exact_installed_base_verified', 'filesystem_readback_verified',
    'all_odm_inode_metadata_preserved', 'erofs_uuid_preserved',
    'unrelated_files_preserved', 'partition_sizes_unchanged', 'odm_hashtree_verified',
    'signatures_verified', 'only_odm_avb_descriptor_changed',
    'embedded_avb_properties_preserved', 'overlay_certificates_preserved',
    'existing_avb_public_key_preserved', 'r9_location_chain_preserved'
)
if ($Revision -eq 12) {
    $checks += @(
        'all_existing_system_inode_bytes_preserved', 'system_external_xattr_blocks_preserved',
        'system_superblock_metadata_preserved', 'system_new_file_metadata_verified',
        'system_filesystem_readback_verified', 'readonly_e2fsck_passed',
        'system_filesystem_changed_blocks_within_scope',
        'system_hashtree_verified', 'only_system_avb_descriptor_changed',
        'system_avb_public_key_preserved', 'system_avb_headers_and_properties_preserved'
    )
}
foreach ($check in $checks) {
    if ($manifest.$check -ne $true) { throw "Image verification missing: $check" }
}
$expectedFiles = $baseline.ChangedFiles
if ((($manifest.changed_odm_files | Sort-Object) -join ',') -ne (($expectedFiles | Sort-Object) -join ',')) {
    throw 'Unexpected ODM image scope.'
}
$expectedOdm = $baseline.OdmSha
$expectedVbmeta = $baseline.VbmetaSha
$expectedExt = '7a4e2a739f9cbc3a9713113e40f8a181dde34875c1ef0abee5e53411de58c573'
$expectedChain = 'c0a925d91b33750a09eea0b99beeb759a37c47ac8736112c802a8adbf68eb0f8'
$expectedSystem = '50cb7ebad3703ca03734f566aa6ea1f462675f4b361c968849b913b33e932089'
$expectedVendor = 'c663a57f003d3cd0791ec2a7b50ad36ed1e1d1d96c0b4b414adc5b3bc63ef038'
if ($manifest.raw_base_sha256 -ne $expectedOdm -or $manifest.raw_base_bytes -ne 1141067776 -or
        $manifest.vbmeta_base_sha256 -ne $expectedVbmeta -or
        $manifest.inherited_image_sha256.system_ext -ne $expectedExt -or
        $manifest.inherited_image_sha256.vbmeta_system -ne $expectedChain -or
        $manifest.inherited_image_sha256.system -ne $expectedSystem -or
        $manifest.inherited_image_sha256.vendor -ne $expectedVendor) { throw 'Unexpected installed baseline.' }
if ($Revision -eq 12) {
    if ($manifest.system_base_sha256 -ne $expectedSystem -or
            $manifest.system_base_bytes -ne 1005133824 -or
            $manifest.vbmeta_system_base_sha256 -ne $expectedChain -or
            $manifest.vbmeta_system_base_bytes -ne 4096) { throw 'Unexpected r12 system baseline.' }
    if (@($manifest.changed_system_files).Count -ne 1 -or
            $manifest.changed_system_files[0] -ne 'etc/device-config-defaults') {
        throw 'Unexpected system image scope.'
    }
    $partitions = @('system', 'vbmeta_system', 'odm', 'vbmeta')
} else {
    $partitions = @('odm', 'vbmeta')
}
$partitionSizes = @{
    system = 1005133824
    vbmeta_system = 4096
    odm = 1141067776
    vbmeta = 8192
}
if (@($manifest.files).Count -ne $partitions.Count -or
        (($manifest.files.partition | Sort-Object) -join ',') -ne (($partitions | Sort-Object) -join ',')) {
    throw 'Unexpected flash partitions.'
}
foreach ($file in $manifest.files) {
    if ($file.name -ne ($file.partition + '.img') -or
            $file.bytes -ne $partitionSizes[$file.partition] -or
            $file.sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Unexpected image size/identity.' }
    $path = Join-Path $imageDirectory $file.name
    if ((Get-Item -LiteralPath $path).Length -ne $file.bytes -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
        throw "Image changed: $($file.name)"
    }
}
$evidenceDirectory = Join-Path $workspace ('reports/device/overlay-r' + $Revision + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
        # Windows PowerShell 5.1 fallback: quote for CreateProcess, never a shell.
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
    $timeoutMs = if ($arguments[0] -eq 'flash') { 180000 } else { 30000 }
    if (-not $process.WaitForExit($timeoutMs)) {
        $process.Kill()
        $process.WaitForExit()
        $partial = $stdout.Result + "`n" + $stderr.Result
        Add-Content -LiteralPath $logPath -Value $partial -Encoding UTF8
        $process.Dispose()
        throw "USB tool timed out during $($arguments[0])."
    }
    $exitCode = $process.ExitCode
    $text = $stdout.Result + "`n" + $stderr.Result
    $process.Dispose()
    Add-Content -LiteralPath $logPath -Value $text -Encoding UTF8
    if ($exitCode -ne 0) { throw $text }
    return $text
}
function Assert-LiveHash([string]$name, [string]$command, [string]$expected) {
    $actual = Invoke-SerialTool $adbPath @('shell', $command)
    if ($actual -notmatch ('(?m)^' + $expected + '\s')) { throw "Installed $name baseline mismatch." }
}
$inventory = & $adbPath devices 2>&1
if ($LASTEXITCODE -ne 0 -or ($inventory -join "`n") -notmatch '(?m)^ca10ede3\s+device\s*$') {
    throw 'The authorized tablet is not connected through ADB.'
}
$product = Invoke-SerialTool $adbPath @('shell', 'getprop ro.product.device')
$slot = Invoke-SerialTool $adbPath @('shell', 'getprop ro.boot.slot_suffix')
$uid = Invoke-SerialTool $adbPath @('shell', 'id -u')
if ($product.Trim() -ne 'sheng' -or $slot.Trim() -ne '_b' -or $uid.Trim() -ne '0') {
    throw 'Device, active slot or root endpoint mismatch.'
}
Assert-LiveHash 'odm_b' 'sha256sum /dev/block/mapper/odm_b' $expectedOdm
Assert-LiveHash 'vbmeta_b prefix' 'dd if=/dev/block/by-name/vbmeta_b bs=8192 count=1 2>/dev/null | sha256sum' $expectedVbmeta
Assert-LiveHash 'r9 system_ext_b' 'sha256sum /dev/block/mapper/system_ext_b' $expectedExt
Assert-LiveHash 'r9 vbmeta_system_b prefix' 'dd if=/dev/block/by-name/vbmeta_system_b bs=4096 count=1 2>/dev/null | sha256sum' $expectedChain
Assert-LiveHash 'r7 system_b' 'sha256sum /dev/block/mapper/system_b' $expectedSystem
Assert-LiveHash 'r6 vendor_b' 'sha256sum /dev/block/mapper/vendor_b' $expectedVendor
Copy-Item -LiteralPath (Join-Path $imageDirectory 'build-result.json') -Destination (Join-Path $evidenceDirectory 'packaging-manifest.json')
Invoke-SerialTool $adbPath @('reboot', 'fastboot') | Write-Output
$deadline = (Get-Date).AddSeconds(90)
$ready = $false
do {
    Start-Sleep -Seconds 3
    try {
        $inventory = Invoke-SerialTool $fastbootPath @('devices')
        if ($inventory -match '(?m)^ca10ede3\s+fastboot(?:\s|$)') {
            $mode = Invoke-SerialTool $fastbootPath @('getvar', 'is-userspace')
            $ready = $mode -match '(?m)^is-userspace:\s*yes\s*$'
        }
    } catch { $ready = $false }
} until ($ready -or (Get-Date) -gt $deadline)
if (-not $ready) { throw 'Fastbootd did not become available.' }
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
Write-Output "Scoped overlay/configuration flash complete; boot and runtime verification pending. Evidence: $evidenceDirectory"
