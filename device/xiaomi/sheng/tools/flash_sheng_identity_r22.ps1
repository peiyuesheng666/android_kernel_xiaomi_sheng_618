param([switch]$Flash)
# Local verification is the default; -Flash applies the r22 batch to slot b.
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$imageDirectory = Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r22'
$serial = 'ca10ede3'
$sizes = @{ odm = 1141067776; system_ext = 572813312; vbmeta = 8192; vbmeta_system = 4096 }
$baselines = @{
    odm = '474e3ceab0be4a75847adce0f0dc44f2793274f7b74587501522cfd6ccb9ffa5'
    vendor = '210bf6f64bc865a8f6834e5b4b1d6fdd965139fec2cef2fda56b9fe978d5fd27'
    vbmeta = 'e1fa13fa8e27976ea2748f0f52714647b8e275ab1f9130388dab1705525a9fb0'
    system = '0f9c8ad6341faae4abaa9c080614d6d879aa62e85e36383086bb0333adfb4dce'
    vbmeta_system = '0ff1a343eea804a4358c34dca8a9178fb6e34a0c480d7200df465f76d0510276'
    system_ext = 'a84b79a184d2ec877b650f33a08fe3c91a4154d5b98b35d503ffdfe808fda8eb'
}
# Packaging deliberately starts system_ext from the verified r20-compatible
# base to omit r21's unused fragment; live preflight still requires exact r21.
$sourceBaselines = @{}
foreach ($name in $baselines.Keys) { $sourceBaselines[$name] = $baselines[$name] }
$sourceBaselines['system_ext'] = '9663016b59a90b30cb573dd45785f01ef1ef0ccefad6572279051cdec92a220a'
$sourceBaselines['vbmeta_system'] = 'bb396433319e6d1f77cb24f6f223b08de107d6e266838bc156c81acf526374e8'

$build = Get-Content -LiteralPath (Join-Path $workspace 'device/xiaomi/sheng/docs/build-r22-identity-tablet-20261107.json') -Raw | ConvertFrom-Json
if ($build.build_passed -ne $true -or $build.resource_link_probe_passed -ne $true -or
        $build.classpath_adapter_tests_passed -ne $true) { throw 'Missing build review.' }
$expectedScope = @{
    odm = @('overlay/SettingsResOverlaySheng.apk', 'overlay/SettingsProviderResOverlaySheng.apk',
        'etc/selinux/precompiled_sepolicy',
        'etc/selinux/precompiled_sepolicy.system_ext_sepolicy_and_mapping.sha256')
    system_ext = @('etc/init/sheng-tablet-compat.rc', 'framework/sheng-tablet-compat.jar',
        'bin/sheng-derive-classpath', 'etc/selinux/system_ext_file_contexts',
        'etc/selinux/system_ext_sepolicy.cil', 'etc/selinux/system_ext_sepolicy_and_mapping.sha256')
}

$reviewed = @{}
foreach ($partition in $build.reviewed_sha256.PSObject.Properties) {
    $reviewed[$partition.Name] = @{}
    foreach ($file in $partition.Value.PSObject.Properties) { $reviewed[$partition.Name][$file.Name] = $file.Value }
}
foreach ($partition in $expectedScope.Keys) {
    if ((($expectedScope[$partition] | Sort-Object) -join ',') -ne
            (($reviewed[$partition].Keys | Sort-Object) -join ',')) { throw 'Unexpected reviewed scope.' }
}
$manifest = Get-Content -LiteralPath (Join-Path $imageDirectory 'build-result.json') -Raw | ConvertFrom-Json
if ($manifest.revision -ne 22 -or $manifest.frozen_spec.revision -ne 22) { throw 'Batch revision mismatch.' }
foreach ($check in @('exact_baselines_verified', 'all_filesystem_stages_verified', 'both_parent_chains_verified')) {
    if ($manifest.$check -ne $true) { throw "Missing batch check: $check" }
}
foreach ($partition in $baselines.Keys) {
    if ($manifest.baseline_sha256.$partition -ne $sourceBaselines[$partition]) { throw "Unexpected baseline: $partition" }
}
if ((($reviewed.Keys | Sort-Object) -join ',') -ne 'odm,system_ext') { throw 'Build review is missing.' }
if ((($manifest.frozen_spec.partitions.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'odm,system_ext') {
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
        @('bin/sheng-derive-classpath', 'etc/init/sheng-tablet-compat.rc', 'framework/sheng-tablet-compat.jar')
    } else { @('overlay/SettingsProviderResOverlaySheng.apk') }
    if (($newNodes -join ',') -ne ($expectedNodes -join ',')) { throw 'Unexpected new nodes.' }
}
if (@($manifest.files).Count -ne 4 -or
        (($manifest.files.partition | Sort-Object) -join ',') -ne 'odm,system_ext,vbmeta,vbmeta_system') {
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
Write-Output 'r22 Settings/tablet images, metadata, signing and both AVB chains verified.'
if (-not $Flash) { return }
$adbPath = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastbootPath = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$evidenceDirectory = Join-Path $workspace ('reports/device/batch-r22-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
        $inventory = Invoke-SerialTool $fastbootPath @('devices')
        if ($inventory -notmatch ('(?m)^' + [regex]::Escape($serial) + '\s+fastboot\s*$')) { continue }
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
foreach ($partition in @('system_ext', 'odm', 'vbmeta_system', 'vbmeta')) {
    Write-Output "Flashing ${partition}_b"
    Invoke-SerialTool $fastbootPath @('flash', ($partition + '_b'),
        (Join-Path $imageDirectory ($partition + '.img'))) | Write-Output
}
Invoke-SerialTool $fastbootPath @('reboot') | Write-Output
