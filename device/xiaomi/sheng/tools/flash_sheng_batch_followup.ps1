param([switch]$Flash)
# r13 image verification is the default. -Flash applies the reviewed batch to slot b.
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$imageDirectory = Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r13'
$serial = 'ca10ede3'
$sizes = @{ system = 1005133824; odm = 1141067776; vendor = 303517696; vbmeta = 8192; vbmeta_system = 4096 }
$baselines = @{
    system = '50cb7ebad3703ca03734f566aa6ea1f462675f4b361c968849b913b33e932089'
    odm = 'd947ae93faad87bcb26da93afe245d6528e04f2b698ca4116257d29262ff5aac'
    vendor = 'c663a57f003d3cd0791ec2a7b50ad36ed1e1d1d96c0b4b414adc5b3bc63ef038'
    vbmeta = '43412dea1eebb58489cd8acfec9368123af94090d3b2665aab225abc61f17e78'
    vbmeta_system = 'c0a925d91b33750a09eea0b99beeb759a37c47ac8736112c802a8adbf68eb0f8'
    system_ext = '7a4e2a739f9cbc3a9713113e40f8a181dde34875c1ef0abee5e53411de58c573'
}
$manifest = Get-Content -LiteralPath (Join-Path $imageDirectory 'build-result.json') -Raw | ConvertFrom-Json
if ($manifest.revision -ne 13 -or $manifest.frozen_spec.revision -ne 13) { throw 'Batch revision mismatch.' }
foreach ($check in @('exact_baselines_verified', 'all_filesystem_stages_verified', 'both_parent_chains_verified')) {
    if ($manifest.$check -ne $true) { throw "Missing batch verification: $check" }
}
foreach ($partition in $baselines.Keys) {
    if ($manifest.baseline_sha256.$partition -ne $baselines[$partition]) { throw "Unexpected baseline: $partition" }
}
if ((($manifest.files.partition | Sort-Object) -join ',') -ne (($sizes.Keys | Sort-Object) -join ',') -or
        @($manifest.files).Count -ne 5) { throw 'Unexpected image set.' }
if ((($manifest.frozen_spec.partitions.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'odm,system,vendor') {
    throw 'Unexpected filesystem partition scope.'
}
$fpc = $manifest.frozen_spec.partitions.odm.files.'lib64/hw/fingerprint.fpc.default.so'
if ($fpc.kind -ne 'symlink' -or $fpc.link_target -ne 'fingerprint.fpc.so' -or
        $fpc.target_sha256 -ne '4388432669c5fe1cc52ebd5a343d190724a2417f60352a804b43b0900939bcbd') {
    throw 'FPC alias contract mismatch.'
}
foreach ($partition in @('system', 'odm', 'vendor')) {
    if ($manifest.partition_reports.$partition.metadata_preserved -ne $true) { throw "Metadata check missing: $partition" }
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
Write-Output 'r13 images, metadata and both AVB chains verified.'
if (-not $Flash) { return }

$adbPath = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastbootPath = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$evidenceDirectory = Join-Path $workspace ('reports/device/batch-r13-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
foreach ($partition in @('system', 'odm', 'vendor', 'vbmeta_system', 'vbmeta')) {
    Write-Output "Flashing ${partition}_b"
    Invoke-SerialTool $fastbootPath @('flash', ($partition + '_b'),
        (Join-Path $imageDirectory ($partition + '.img'))) | Write-Output
}
Invoke-SerialTool $fastbootPath @('reboot') | Write-Output
