param()
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$adb = Join-Path $workspace 'tools/platform-tools/adb.exe'
$serial = 'ca10ede3'
$manifest = Get-Content -Raw -LiteralPath (Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r23/build-result.json') | ConvertFrom-Json
$accepted = Get-Content -Raw -LiteralPath (Join-Path $workspace 'device/xiaomi/sheng/docs/runtime-r22-identity-tablet-20261107.json') | ConvertFrom-Json
$evidence = Join-Path $workspace ('reports/device/r23-runtime-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $evidence | Out-Null
function Invoke-Adb([string[]]$arguments) {
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $adb
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($argument in (@('-s', $serial) + $arguments)) { $start.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    if (-not $process.Start()) { throw 'Unable to start target ADB.' }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(45000)) { $process.Kill(); throw 'Target ADB timed out.' }
    $output = $stdout.Result + "`n" + $stderr.Result
    $code = $process.ExitCode
    $process.Dispose()
    if ($code -ne 0) {
        Add-Content -LiteralPath (Join-Path $evidence 'command-failures.txt') -Value $output -Encoding utf8
        throw $output
    }
    return $output
}
function Save-Shell([string]$name, [string]$command) {
    $value = Invoke-Adb @('shell', $command)
    Set-Content -LiteralPath (Join-Path $evidence $name) -Value $value -Encoding utf8
    return $value
}
if ((Invoke-Adb @('shell', 'getprop ro.product.device')).Trim() -ne 'sheng' -or
    (Invoke-Adb @('shell', 'getprop ro.boot.slot_suffix')).Trim() -ne '_b' -or
    (Invoke-Adb @('shell', 'getprop sys.boot_completed')).Trim() -ne '1' -or
    (Invoke-Adb @('shell', 'id -u')).Trim() -ne '0') {
    throw 'Wrong device, slot, incomplete boot or non-root endpoint. This tool never runs adb root.'
}
$hashes = @{}
foreach ($partition in @('system', 'system_ext', 'odm', 'vendor', 'vbmeta', 'vbmeta_system')) {
    $expected = $accepted.installed_partition_hashes.$partition
    if ($partition -in @('vendor', 'vbmeta')) {
        $expected = ($manifest.files | Where-Object partition -eq $partition).sha256
    }
    $command = if ($partition -in @('vbmeta', 'vbmeta_system')) {
        $bytes = if ($partition -eq 'vbmeta') { 8192 } else { 4096 }
        "dd if=/dev/block/by-name/${partition}_b bs=$bytes count=1 2>/dev/null | sha256sum"
    } else { "sha256sum /dev/block/mapper/${partition}_b" }
    $value = Save-Shell ($partition + '-hash.txt') $command
    if ($value -notmatch ('(?m)^' + $expected + '\s')) { throw "Installed hash mismatch: $partition" }
    $hashes[$partition] = $expected
}
$state = Save-Shell 'identity-state.txt' 'getprop ro.product.model; getprop ro.product.marketname; getprop ro.build.characteristics; getenforce; settings get secure adaptive_sleep; settings get system screen_off_timeout; cat /proc/sys/kernel/random/boot_id; cat /proc/uptime'
if ((Invoke-Adb @('shell', 'getprop ro.product.model')).Trim() -ne '24018RPACC' -or
    (Invoke-Adb @('shell', 'getprop ro.product.marketname')).Trim() -ne 'Xiaomi Pad 6S Pro 12.4' -or
    (Invoke-Adb @('shell', 'getenforce')).Trim() -ne 'Enforcing' -or
    (Invoke-Adb @('shell', 'settings get secure adaptive_sleep')).Trim() -ne '1' -or
    (Invoke-Adb @('shell', 'settings get system screen_off_timeout')).Trim() -ne '15000') {
    throw 'Identity, SELinux or preserved attention setting mismatch.'
}
$link = Save-Shell 'aon-link.txt' 'readlink /vendor/lib64/camera/aon_front.pb; sha256sum /vendor/lib64/camera/aon_front.pb /odm/lib64/camera/aon_front.pb; ls -lZ /vendor/lib64/camera/aon_front.pb /odm/lib64/camera/aon_front.pb'
if ($link -notmatch '(?m)^/odm/lib64/camera/aon_front.pb\s*$' -or
    @([regex]::Matches($link, 'b0d920c16e4968173cf8f4f90c1056e959b9aad1c2651a76cca17ee19dac46d6')).Count -ne 2) {
    throw 'AON alias or unchanged target hash mismatch.'
}
Save-Shell 'services-before.txt' 'lshal -i; ps -A | grep -E "dolby|codec2"' | Out-Null
$binaries = Save-Shell 'dolby-binary-hashes.txt' 'sha256sum /vendor/bin/hw/dolbycodec2 /vendor/bin/hw/vendor.dolby.media.c2@1.0-service'
foreach ($relative in @('bin/hw/dolbycodec2', 'bin/hw/vendor.dolby.media.c2@1.0-service')) {
    $expected = $manifest.frozen_spec.partitions.vendor.files.$relative.sha256
    if ($binaries -notmatch ('(?m)^' + $expected + '\s')) { throw "Running binary differs from reviewed allocation: $relative" }
}
$remoteNative = '/data/local/tmp/sheng-codec2-hal-probe-r23'
$remoteJava = '/data/local/tmp/sheng-codec2-audio-probe-r23.jar'
if ((Invoke-Adb @('shell', "test ! -e $remoteNative && test ! -e $remoteJava; echo `$?")).Trim() -ne '0') {
    throw 'Temporary probe path already exists.'
}
try {
    Invoke-Adb @('push', (Join-Path $workspace 'artifacts/audio-diagnostics-sheng/sheng-codec2-hal-probe-r23'), $remoteNative) | Out-Null
    Invoke-Adb @('push', (Join-Path $workspace 'artifacts/audio-diagnostics-sheng/sheng-codec2-audio-probe-r23.jar'), $remoteJava) | Out-Null
    Invoke-Adb @('shell', "chmod 700 $remoteNative") | Out-Null
    Save-Shell 'hal-probe.txt' "timeout 30 env LD_LIBRARY_PATH=/vendor/lib64:/system/lib64 $remoteNative" | Out-Null
    Save-Shell 'mediacodec-probe.txt' "timeout 30 env CLASSPATH=$remoteJava app_process /system/bin ShengCodec2Probe --decoders-only --audio-only" | Out-Null
} finally {
    Invoke-Adb @('shell', "rm -f $remoteNative $remoteJava") | Out-Null
}
Save-Shell 'services-after.txt' 'lshal -i; ps -A | grep -E "dolby|codec2"' | Out-Null
$logs = Save-Shell 'startup-logcat.txt' 'logcat -b all -d'
Save-Shell 'crash-buffer.txt' 'logcat -b crash -d' | Out-Null
$allocationLogged = $logs -match 'dolby: registered, ComponentStore size=288' -and
    $logs -match 'default1: registered, ComponentStore size=288'
if ($logs -match 'Cmdline: /vendor/bin/hw/(dolbycodec2|vendor\.dolby\.media\.c2@1\.0-service)') {
    throw 'Current boot contains a Dolby service native crash.'
}
$result = [ordered]@{
    revision = 23; serial = $serial; slot = 'b'; hardware_boot_tested = $true
    installed_partition_hashes = $hashes; all_six_partition_hashes_match = $true
    exact_component_store_size = 288; both_hal_stores_verified = $true
    media_codec_audio_decoder_allocation_verified = $true; aon_alias_verified = $true
    allocation_size_evidence = 'Installed binary hashes match reviewed 288-byte allocation disassembly'
    both_allocation_registration_logs_retained = [bool]$allocationLogged
    video_encoder_accepted = $false
    video_decoder_post_release_idle_verified = $false
    aon_user_test_passed = $null; audiovisual_user_regression_passed = $null
    temporary_probes_cleaned = $true; other_connected_device_operated = $false
    evidence_directory = $evidence
}
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidence 'runtime-result.json') -Encoding utf8
Write-Output $evidence
