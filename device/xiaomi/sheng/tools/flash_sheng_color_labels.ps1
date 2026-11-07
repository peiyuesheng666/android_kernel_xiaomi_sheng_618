param([switch]$Flash)
# Verify locally by default; explicit -Flash updates only the reviewed r17 batch.
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$imageDirectory = Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r17'
$serial = 'ca10ede3'
$sizes = @{ odm = 1141067776; vbmeta = 8192 }
$baselines = @{
    odm = 'de7f436b7a6ee7cf4ac6e6bd8573e36dd0e855a24fb0e981d1c9b001af3191c2'
    vendor = 'de2ca07b44743f201bd911c11e54ce60134463c3f4e83589b6413c537e7d02de'
    vbmeta = 'a31fa81b932e9e2ae645de6c2cd476c6449f6553a3692812ef5390b05812f1e3'
    system = '0551a74f4f995793665a485d10caacffb22ccd8fdaffb78d7811d17c658b3ac1'
    vbmeta_system = 'a947be896074811b496f42cf3759def63f808518869f56ed6c67c608622cd165'
    system_ext = '7a4e2a739f9cbc3a9713113e40f8a181dde34875c1ef0abee5e53411de58c573'
}
$scope = @{
    odm = @('overlay/SettingsResOverlaySheng.apk')
}
$manifest = Get-Content -LiteralPath (Join-Path $imageDirectory 'build-result.json') -Raw | ConvertFrom-Json
if ($manifest.revision -ne 17 -or $manifest.frozen_spec.revision -ne 17) { throw 'Display batch revision mismatch.' }
if ($manifest.frozen_spec.partitions.odm.'overlay/SettingsResOverlaySheng.apk'.sha256 -ne
        '83600de78c26df4221e44d70df5ab866c756d34fee68f9623512aa17aa95f71f') {
    throw 'r17 must contain the compiled color-label Settings overlay.'
}
foreach ($check in @('exact_baselines_verified', 'all_filesystem_stages_verified', 'vbmeta_parent_verified')) {
    if ($manifest.$check -ne $true) { throw "Missing display batch check: $check" }
}
foreach ($partition in $baselines.Keys) {
    if ($manifest.baseline_sha256.$partition -ne $baselines[$partition]) { throw "Unexpected baseline: $partition" }
}
if ((($manifest.frozen_spec.partitions.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'odm') {
    throw 'Unexpected filesystem partition scope.'
}
foreach ($partition in $scope.Keys) {
    $expected = ($scope[$partition] | Sort-Object) -join ','
    $actual = ($manifest.frozen_spec.partitions.$partition.PSObject.Properties.Name | Sort-Object) -join ','
    $reported = ($manifest.partition_reports.$partition.changed_files | Sort-Object) -join ','
    if ($actual -ne $expected -or $reported -ne $expected -or
            $manifest.partition_reports.$partition.metadata_preserved -ne $true) {
        throw "Unexpected file/metadata scope: $partition"
    }
}
if (@($manifest.files).Count -ne 2 -or
        (($manifest.files.partition | Sort-Object) -join ',') -ne 'odm,vbmeta') {
    throw 'Unexpected image set.'
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
Write-Output 'r17 display images, metadata and AVB parent verified.'
if (-not $Flash) { return }
$adbPath = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastbootPath = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$evidenceDirectory = Join-Path $workspace ('reports/device/batch-r17-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
foreach ($partition in @('odm', 'vbmeta')) {
    Write-Output "Flashing ${partition}_b"
    Invoke-SerialTool $fastbootPath @('flash', ($partition + '_b'),
        (Join-Path $imageDirectory ($partition + '.img'))) | Write-Output
}
Invoke-SerialTool $fastbootPath @('reboot') | Write-Output
