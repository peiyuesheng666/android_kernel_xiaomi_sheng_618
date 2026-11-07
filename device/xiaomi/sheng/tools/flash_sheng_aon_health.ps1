param([switch]$Flash)
# Local verification is the default; -Flash applies the r19 batch to slot b.
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$imageDirectory = Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r19'
$serial = 'ca10ede3'
$sizes = @{ odm = 1141067776; vendor = 303517696; system_ext = 572813312; vbmeta = 8192; vbmeta_system = 4096 }
$baselines = @{
    odm = 'ecc21d624a0b5c5f31552001d62d815c73d5762dc5a041af4361bce91d2e5bb5'
    vendor = 'de2ca07b44743f201bd911c11e54ce60134463c3f4e83589b6413c537e7d02de'
    vbmeta = '1d6b64b741611cfab318794aa29d4a50fe4e3cde6b18c1131e310f27bd20dada'
    system = '0551a74f4f995793665a485d10caacffb22ccd8fdaffb78d7811d17c658b3ac1'
    vbmeta_system = 'a947be896074811b496f42cf3759def63f808518869f56ed6c67c608622cd165'
    system_ext = '7a4e2a739f9cbc3a9713113e40f8a181dde34875c1ef0abee5e53411de58c573'
}
# Reviewed combined r19 build inputs.
$reviewed = @{
    odm = @{
        'etc/selinux/precompiled_sepolicy' = '8317106950e7f99da8dd80691b028771c57d441752ae6ff58e6648739ce99374'
        'overlay/FrameworkResOverlaySheng.apk' = 'c75aa44932b9f637723fe95b7b25dec8b004c3e6d766894c3d9a8b251310483e'
    }
    vendor = @{
        'bin/hw/android.hardware.health-service.sheng' = '07b3145d9ba4c1b93ad7cb3cfc11ec663a707258b3aeefb50cf6218e3c613011'
        'etc/init/android.hardware.health-service.sheng.rc' = '2429ec9215c8ca47ff704415db2416cfad6dabd8063ce14e0beb9def81d38c0e'
        'etc/selinux/vendor_file_contexts' = '8378fbe17737d5b36f168efd982cb7859d4d102fe197c7ee2efd55a1ac991dcf'
        'etc/selinux/vendor_sepolicy.cil' = 'b9849a0178c4c35bdc09e2d4d8aa87181c8421dd5a8cc2ab532c1403f4f7221a'
        'etc/selinux/vendor_service_contexts' = 'c07e9275cc1f43cf0b076442fd74e977f5972624e046c3087b6c3efc1200f778'
        'etc/vintf/manifest.xml' = '6a94b185039d32e2d16b98efeeb8db1d91d720e82ab4226cf2bc972427e493b5'
    }
    system_ext = @{
        'app/MiAONService/MiAONService.apk' = '3f5adb243442c3a5d4c88fbe35a61243f205624754d1a441a6ede27caf744625'
    }
}
$manifest = Get-Content -LiteralPath (Join-Path $imageDirectory 'build-result.json') -Raw | ConvertFrom-Json
if ($manifest.revision -ne 19 -or $manifest.frozen_spec.revision -ne 19) { throw 'Batch revision mismatch.' }
foreach ($check in @('exact_baselines_verified', 'all_filesystem_stages_verified', 'both_parent_chains_verified')) {
    if ($manifest.$check -ne $true) { throw "Missing batch check: $check" }
}
foreach ($partition in $baselines.Keys) {
    if ($manifest.baseline_sha256.$partition -ne $baselines[$partition]) { throw "Unexpected baseline: $partition" }
}
if ((($reviewed.Keys | Sort-Object) -join ',') -ne 'odm,system_ext,vendor') { throw 'Build review is missing.' }
if ((($manifest.frozen_spec.partitions.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'odm,system_ext,vendor') {
    throw 'Unexpected filesystem scope.'
}
foreach ($partition in $reviewed.Keys) {
    $stage = $manifest.frozen_spec.partitions.$partition
    $expected = ($reviewed[$partition].Keys | Sort-Object) -join ','
    $actual = ($stage.files.PSObject.Properties.Name | Sort-Object) -join ','
    $reported = ($manifest.partition_reports.$partition.changed_files | Sort-Object) -join ','
    if ($actual -ne $expected -or $reported -ne $expected -or
            $manifest.partition_reports.$partition.metadata_preserved -ne $true) {
        throw "Unexpected file or metadata scope: $partition"
    }
    foreach ($path in $reviewed[$partition].Keys) {
        if ($stage.files.$path.sha256 -ne $reviewed[$partition][$path]) { throw "Unreviewed build input: $path" }
    }
    $newNodes = @($stage.new_nodes.PSObject.Properties.Name | Sort-Object)
    $expectedNodes = if ($partition -eq 'system_ext') {
        @('app/MiAONService', 'app/MiAONService/MiAONService.apk')
    } elseif ($partition -eq 'vendor') {
        @('bin/hw/android.hardware.health-service.sheng', 'etc/init/android.hardware.health-service.sheng.rc')
    } else { @() }
    if (($newNodes -join ',') -ne ($expectedNodes -join ',')) { throw 'Unexpected new nodes.' }
}
if (@($manifest.files).Count -ne 5 -or
        (($manifest.files.partition | Sort-Object) -join ',') -ne 'odm,system_ext,vbmeta,vbmeta_system,vendor') {
    throw 'Unexpected image set.'
}
if (@($manifest.platform_certificate).Count -ne 1 -or $manifest.platform_certificate[0] -ne
        'c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8') {
    throw 'Unexpected platform signing reference.'
}
foreach ($file in $manifest.files) {
    if ($file.name -ne ($file.partition + '.img') -or $file.bytes -ne $sizes[$file.partition] -or
            $file.sha256 -notmatch '^[0-9a-f]{64}$') { throw 'Invalid image identity or size.' }
    $path = Join-Path $imageDirectory $file.name
    $item = Get-Item -LiteralPath $path -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -ne $file.bytes -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
        throw "Image changed: $($file.name)"
    }
}
Write-Output 'r19 AON/Health images, metadata, signing and both AVB chains verified.'
if (-not $Flash) { return }
$adbPath = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastbootPath = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$evidenceDirectory = Join-Path $workspace ('reports/device/batch-r19-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
function Assert-LiveHash([string]$name, [string]$command) {
    $output = Invoke-SerialTool $adbPath @('shell', $command)
    if ($output -notmatch ('(?m)^' + $baselines[$name] + '\s')) { throw "Installed baseline mismatch: $name" }
}
$product = Invoke-SerialTool $adbPath @('shell', 'getprop ro.product.device')
$slot = Invoke-SerialTool $adbPath @('shell', 'getprop ro.boot.slot_suffix')
$uid = Invoke-SerialTool $adbPath @('shell', 'id -u')
if ($product.Trim() -ne 'sheng' -or $slot.Trim() -ne '_b' -or $uid.Trim() -ne '0') {
    throw 'Device, slot or root endpoint mismatch.'
}
foreach ($partition in @('system', 'system_ext', 'odm', 'vendor')) {
    Assert-LiveHash $partition ('sha256sum /dev/block/mapper/' + $partition + '_b')
}
Assert-LiveHash 'vbmeta' 'dd if=/dev/block/by-name/vbmeta_b bs=8192 count=1 2>/dev/null | sha256sum'
Assert-LiveHash 'vbmeta_system' 'dd if=/dev/block/by-name/vbmeta_system_b bs=4096 count=1 2>/dev/null | sha256sum'
Copy-Item -LiteralPath (Join-Path $imageDirectory 'build-result.json') -Destination (Join-Path $evidenceDirectory 'packaging-manifest.json')
Invoke-SerialTool $adbPath @('reboot', 'fastboot') | Write-Output
$deadline = (Get-Date).AddSeconds(90)
$ready = $false
do {
    Start-Sleep -Seconds 3
    try {
        $mode = Invoke-SerialTool $fastbootPath @('getvar', 'is-userspace')
        $ready = $mode -match '(?m)^is-userspace:\s*yes\s*$'
    } catch { $ready = $false }
} until ($ready -or (Get-Date) -gt $deadline)
if (-not $ready) { throw 'Fastbootd did not become available.' }
$product = Invoke-SerialTool $fastbootPath @('getvar', 'product')
$slot = Invoke-SerialTool $fastbootPath @('getvar', 'current-slot')
if ($product -notmatch '(?m)^product:\s*sheng\s*$' -or $slot -notmatch '(?m)^current-slot:\s*b\s*$') {
    throw 'Fastbootd device or slot mismatch.'
}
foreach ($partition in @('system_ext', 'odm', 'vendor', 'vbmeta_system', 'vbmeta')) {
    Write-Output "Flashing ${partition}_b"
    Invoke-SerialTool $fastbootPath @('flash', ($partition + '_b'),
        (Join-Path $imageDirectory ($partition + '.img'))) | Write-Output
}
Invoke-SerialTool $fastbootPath @('reboot') | Write-Output
