param([switch]$Flash)
# Restore the accepted r22 SystemUI partition and its AVB parent from exact r24.
# Keep the independently built r24 vendor repair; never erase data or switch slots.
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$imageDirectory = Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r22'
$serial = 'ca10ede3'
$restoreHashes = @{
    system_ext = '82006f12228ebda0a521a96f8373c48bb52edb981a790830304f8ea50aa60419'
    vbmeta_system = '3fe3413cc7fe8786372606ebfe7f9470e41bbf34b1dbcb5db7397540d9afc26a'
}
$sizes = @{ system_ext = 572813312; vbmeta_system = 4096 }
$baselines = @{
    system = '0f9c8ad6341faae4abaa9c080614d6d879aa62e85e36383086bb0333adfb4dce'
    system_ext = 'dec8a7e4dc8adc931ab6998d204a4f21b058b16af28a8615ef17fe8bf25811cc'
    odm = 'c315f3e80f292909740d3e052102dcabb36b3f3bcaa817918f9dbc92630ce651'
    vendor = '4aa0518217ad9521d044b7408348039eb88457fa855bc3544cb499fea0299026'
    vbmeta = '883ba3ee6d22460c8a14f5a0eb04aabb4544d1d48d2386de52715b16ca7a9493'
    vbmeta_system = '644b62ff23dbf89775a5870b517d36a74fa13e9cefaa0d24a97ef5c9dea5014f'
}
$manifest = Get-Content -LiteralPath (Join-Path $imageDirectory 'build-result.json') -Raw | ConvertFrom-Json
if ($manifest.revision -ne 22) { throw 'Recovery source must be the accepted r22 batch.' }
foreach ($partition in $restoreHashes.Keys) {
    $record = @($manifest.files | Where-Object partition -EQ $partition)
    if ($record.Count -ne 1 -or $record[0].sha256 -ne $restoreHashes[$partition] -or
            $record[0].bytes -ne $sizes[$partition]) { throw "Restore manifest mismatch: $partition" }
    $path = Join-Path $imageDirectory ($partition + '.img')
    $item = Get-Item -LiteralPath $path -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -ne $sizes[$partition] -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $restoreHashes[$partition]) {
        throw "Accepted r22 image changed: $partition"
    }
}
Write-Output 'Accepted r22 system_ext and vbmeta_system hashes verified; rollback ready.'
if (-not $Flash) { return }
$adbPath = Join-Path $workspace 'tools/platform-tools/adb.exe'
$fastbootPath = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$evidenceDirectory = Join-Path $workspace ('reports/device/rollback-r24-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
foreach ($partition in @('system_ext', 'vbmeta_system')) {
    Write-Output "Flashing ${partition}_b"
    Invoke-SerialTool $fastbootPath @('flash', ($partition + '_b'),
        (Join-Path $imageDirectory ($partition + '.img'))) | Write-Output
}
Invoke-SerialTool $fastbootPath @('reboot') | Write-Output
