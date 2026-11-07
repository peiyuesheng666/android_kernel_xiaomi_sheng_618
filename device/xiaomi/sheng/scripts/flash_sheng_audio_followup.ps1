param([int]$Revision = 5)
# Flash only the verified device-owned followup; leave reboot checks interactive.
$ErrorActionPreference = 'Stop'
if ($Revision -lt 5) { throw 'Audio followups start at revision 5.' }
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$adbPath = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastbootPath = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$serial = 'ca10ede3'
$imageDirectory = Join-Path $workspace "artifacts/system-hardware-followup-sheng-r$Revision"
$manifest = Get-Content -LiteralPath (Join-Path $imageDirectory 'build-result.json') -Raw | ConvertFrom-Json
foreach ($check in @('readback_verified', 'signatures_verified', 'partition_sizes_unchanged',
        'existing_erofs_inode_metadata_unchanged', 'unrelated_avb_descriptors_preserved',
        'apk_certificate_preserved', 'installed_public_policy_ids_matched', 'native_device_pal_input_verified')) {
    if ($manifest.$check -ne $true) { throw "Missing image verification: $check" }
}
$partitions = @('vendor', 'odm', 'system_ext', 'vbmeta', 'vbmeta_system')
if (($manifest.files.partition | Sort-Object) -join ',' -ne ($partitions | Sort-Object) -join ',') {
    throw 'Unexpected partition set.'
}
foreach ($file in $manifest.files) {
    if ($file.name -ne ($file.partition + '.img')) { throw 'Unexpected image name.' }
    $image = Join-Path $imageDirectory $file.name
    if ((Get-Item -LiteralPath $image).Length -ne $file.bytes -or
            (Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
        throw "Image changed: $($file.name)"
    }
}
$evidenceDirectory = Join-Path $workspace ('reports/device/audio-r' + $Revision + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
$product = Invoke-SerialTool $adbPath @('shell', 'getprop ro.product.device')
$slot = Invoke-SerialTool $adbPath @('shell', 'getprop ro.boot.slot_suffix')
if ($product.Trim() -ne 'sheng' -or $slot.Trim() -ne '_b') { throw 'Device or active slot mismatch.' }
Invoke-SerialTool $adbPath @('shell', 'cat /data/user_de/0/org.lineageos.sheng.dolby/shared_prefs/atmos.xml') |
    Set-Content -LiteralPath (Join-Path $evidenceDirectory 'latest-dolby-preferences.xml') -Encoding UTF8
Invoke-SerialTool $adbPath @('reboot', 'fastboot') | Write-Output
$deadline = (Get-Date).AddSeconds(90)
$ready = $false
do {
    Start-Sleep -Seconds 3
    try {
        $userspace = Invoke-SerialTool $fastbootPath @('getvar', 'is-userspace')
        $ready = $userspace -match '(?m)^is-userspace:\s*yes\s*$'
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
Write-Output "Flash complete; reboot validation pending. Evidence: $evidenceDirectory"
