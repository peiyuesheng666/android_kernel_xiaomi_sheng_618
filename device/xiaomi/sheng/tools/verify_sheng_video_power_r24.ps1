param()
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$adb = Join-Path $workspace 'tools/platform-tools/adb.exe'
$serial = 'ca10ede3'
$manifest = Get-Content -Raw -LiteralPath (Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r24/build-result.json') | ConvertFrom-Json
$accepted = Get-Content -Raw -LiteralPath (Join-Path $workspace 'device/xiaomi/sheng/docs/runtime-r22-identity-tablet-20261107.json') | ConvertFrom-Json
$evidence = Join-Path $workspace ('reports/device/r24-runtime-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
    if (-not $process.WaitForExit(60000)) { $process.Kill(); throw 'Target ADB timed out.' }
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
    if ($partition -in @('vendor', 'system_ext', 'vbmeta', 'vbmeta_system')) {
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
$libraries = Save-Shell 'reviewed-output-hashes.txt' 'sha256sum /vendor/lib64/c2.dolby.hevc.dec.so /vendor/lib64/c2.dolby.hevc.sec.dec.so /system_ext/priv-app/SystemUI/SystemUI.apk'
foreach ($partition in @('vendor', 'system_ext')) {
    foreach ($property in $manifest.frozen_spec.partitions.$partition.files.PSObject.Properties) {
        if ($libraries -notmatch ('(?m)^' + $property.Value.sha256 + '\s')) {
            throw "Running output differs from reviewed file: $($property.Name)"
        }
    }
}
$binaryReview = Get-Content -Raw -LiteralPath (Join-Path $workspace 'device/xiaomi/sheng/docs/build-r23-codec2-aon-20261107.json') | ConvertFrom-Json
$binaries = Save-Shell 'dolby-binary-hashes.txt' 'sha256sum /vendor/bin/hw/dolbycodec2 /vendor/bin/hw/vendor.dolby.media.c2@1.0-service'
foreach ($relative in @('bin/hw/dolbycodec2', 'bin/hw/vendor.dolby.media.c2@1.0-service')) {
    if ($binaries -notmatch ('(?m)^' + $binaryReview.reviewed_sha256.$relative + '\s')) {
        throw "r23 allocation binary changed: $relative"
    }
}
function Get-CodecCpu([string]$tag) {
    $text = Save-Shell ($tag + '.txt') 'for p in $(pidof dolbycodec2 vendor.dolby.media.c2@1.0-service); do cat /proc/$p/stat; done'
    $samples = @{}
    foreach ($line in ($text -split "`n")) {
        if ($line -match '^(\d+) \(.+\) (.+)$') {
            $fields = $Matches[2] -split ' '
            $samples[$Matches[1]] = [long]$fields[11] + [long]$fields[12]
        }
    }
    if ($samples.Count -ne 2) { throw 'Expected both Dolby service processes.' }
    return $samples
}
$before = Get-CodecCpu 'cpu-before'
$systemUiBefore = (Save-Shell 'systemui-process-before.txt' 'pidof com.android.systemui').Trim()
if ($systemUiBefore -notmatch '^\d+$' -or
    (Save-Shell 'systemui-package-path.txt' 'pm path com.android.systemui').Trim() -ne
        'package:/system_ext/priv-app/SystemUI/SystemUI.apk') { throw 'SystemUI process or installed path mismatch.' }
$remoteNative = '/data/local/tmp/sheng-codec2-hal-probe-r23'
$remoteJava = '/data/local/tmp/sheng-codec2-audio-probe-r23.jar'
if ((Invoke-Adb @('shell', "test ! -e $remoteNative && test ! -e $remoteJava; echo `$?")).Trim() -ne '0') {
    throw 'Temporary probe path already exists.'
}
try {
    Invoke-Adb @('push', (Join-Path $workspace 'artifacts/audio-diagnostics-sheng/sheng-codec2-hal-probe-r23'), $remoteNative) | Out-Null
    Invoke-Adb @('push', (Join-Path $workspace 'artifacts/audio-diagnostics-sheng/sheng-codec2-audio-probe-r23.jar'), $remoteJava) | Out-Null
    Invoke-Adb @('shell', "chmod 700 $remoteNative") | Out-Null
    $hal = Save-Shell 'hal-probe.txt' "timeout 30 env LD_LIBRARY_PATH=/vendor/lib64:/system/lib64 $remoteNative"
    if ($hal -notmatch 'Both Dolby stores passed listComponents and createInterface\.') {
        throw 'Both HAL interface checks did not finish.'
    }
    $media = Save-Shell 'mediacodec-all-components.txt' "timeout 45 env CLASSPATH=$remoteJava app_process /system/bin ShengCodec2Probe"
    foreach ($name in @('c2.dolby.ac4.decoder', 'c2.dolby.eac3.decoder.ac3',
        'c2.dolby.eac3.decoder.eac3', 'c2.dolby.eac3.decoder.eac3-joc',
        'c2.dolby.decoder.hevc', 'c2.dolby.encoder.hevc')) {
        if ($media -notmatch ('(?m)^allocated=' + [regex]::Escape($name) + '\s*$')) {
            throw "MediaCodec component was not allocated and released: $name"
        }
    }
    if ($media -notmatch '(?m)^dolby_components=7 allocated=6\s*$') { throw 'Unexpected MediaCodec component coverage.' }
} finally {
    Invoke-Adb @('shell', "rm -f $remoteNative $remoteJava") | Out-Null
}
$afterLifecycle = Get-CodecCpu 'cpu-after-lifecycle'
Start-Sleep -Seconds 5
$afterIdle = Get-CodecCpu 'cpu-after-idle'
$cpuDelta = @{}
foreach ($processId in $before.Keys) {
    if (-not $afterLifecycle.ContainsKey($processId) -or -not $afterIdle.ContainsKey($processId)) {
        throw 'Dolby service restarted during lifecycle validation.'
    }
    $cpuDelta[$processId] = $afterIdle[$processId] - $afterLifecycle[$processId]
    if ($cpuDelta[$processId] -gt 5 -or $cpuDelta[$processId] -lt 0) {
        throw "Dolby service not idle after lifecycle: $processId"
    }
}
Save-Shell 'services-after.txt' 'lshal -i; ps -A | grep -E "dolby|codec2"' | Out-Null
$systemUiAfter = (Save-Shell 'systemui-process-after.txt' 'pidof com.android.systemui').Trim()
if ($systemUiAfter -ne $systemUiBefore) { throw 'SystemUI restarted during automatic regression.' }
$logs = Save-Shell 'startup-logcat.txt' 'logcat -b all -d'
Save-Shell 'crash-buffer.txt' 'logcat -b crash -d' | Out-Null
$allocationLogged = $logs -match 'dolby: registered, ComponentStore size=288' -and
    $logs -match 'default1: registered, ComponentStore size=288'
if ($logs -match 'Cmdline: /vendor/bin/hw/(dolbycodec2|vendor\.dolby\.media\.c2@1\.0-service)') {
    throw 'Current boot contains a Dolby service native crash.'
}
if ($logs -match 'Process: com\.android\.systemui, PID:|Cmdline: com\.android\.systemui\s') {
    throw 'Current boot contains a SystemUI crash.'
}
$result = [ordered]@{
    revision = 24; serial = $serial; slot = 'b'; hardware_boot_tested = $true
    installed_partition_hashes = $hashes; all_six_partition_hashes_match = $true
    exact_component_store_size = 288; both_hal_stores_verified = $true
    media_codec_all_component_allocation_release_verified = $true; aon_alias_verified = $true
    allocation_size_evidence = 'Installed binary hashes match reviewed 288-byte allocation disassembly'
    both_allocation_registration_logs_retained = [bool]$allocationLogged
    video_encoder_allocation_release_verified = $true
    video_decoder_post_release_idle_verified = $true; idle_cpu_ticks_5_seconds = $cpuDelta
    media_codec_allocation_count = 6; systemui_process_stable = $true
    video_stream_decode_verified = $false; power_button_animation_user_passed = $null; aon_user_test_passed = $null; audiovisual_user_regression_passed = $null
    temporary_probes_cleaned = $true; other_connected_device_operated = $false
    evidence_directory = $evidence
}
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidence 'runtime-result.json') -Encoding utf8
Write-Output $evidence
