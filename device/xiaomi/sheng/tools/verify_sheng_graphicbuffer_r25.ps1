param()
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$adb = Join-Path $workspace 'tools/platform-tools/adb.exe'
$serial = 'ca10ede3'
$manifest = Get-Content -Raw -LiteralPath (Join-Path $workspace 'artifacts/system-hardware-followup-sheng-r25/build-result.json') | ConvertFrom-Json
$review = Get-Content -Raw -LiteralPath (Join-Path $workspace 'device/xiaomi/sheng/docs/build-r25-graphicbuffer-20261108.json') | ConvertFrom-Json
$evidence = Join-Path $workspace ('reports/device/r25-runtime-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
if ($manifest.revision -ne 25 -or $review.build_passed -ne $true -or
    $review.graphic_buffer_bytes -ne 3376 -or $review.allocation_sites -ne 14) { throw 'Unreviewed batch.' }
if ((Invoke-Adb @('shell', 'getprop ro.product.device')).Trim() -ne 'sheng' -or
    (Invoke-Adb @('shell', 'getprop ro.boot.slot_suffix')).Trim() -ne '_b' -or
    (Invoke-Adb @('shell', 'getprop sys.boot_completed')).Trim() -ne '1' -or
    (Invoke-Adb @('shell', 'id -u')).Trim() -ne '0') {
    throw 'Wrong device, slot, incomplete boot or non-root endpoint. This tool never runs adb root.'
}
$expected = @{
    system = '0f9c8ad6341faae4abaa9c080614d6d879aa62e85e36383086bb0333adfb4dce'
    system_ext = 'dec8a7e4dc8adc931ab6998d204a4f21b058b16af28a8615ef17fe8bf25811cc'
    vbmeta_system = '644b62ff23dbf89775a5870b517d36a74fa13e9cefaa0d24a97ef5c9dea5014f'
}
foreach ($file in $manifest.files) { $expected[$file.partition] = $file.sha256 }
if ($expected.Count -ne 6) { throw 'Unexpected partition coverage.' }
foreach ($partition in $expected.Keys) {
    $command = if ($partition -in @('vbmeta', 'vbmeta_system')) {
        $bytes = if ($partition -eq 'vbmeta') { 8192 } else { 4096 }
        "dd if=/dev/block/by-name/${partition}_b bs=$bytes count=1 2>/dev/null | sha256sum"
    } else { "sha256sum /dev/block/mapper/${partition}_b" }
    $value = Save-Shell ($partition + '-hash.txt') $command
    if ($value -notmatch ('(?m)^' + $expected[$partition] + '\s')) { throw "Installed hash mismatch: $partition" }
}
$state = Save-Shell 'identity-state.txt' 'getprop ro.product.model; getprop ro.product.marketname; getprop ro.build.characteristics; getenforce; settings get secure adaptive_sleep; settings get system screen_off_timeout; cat /proc/sys/kernel/random/boot_id; cat /proc/uptime'
foreach ($condition in @(
    @('getprop ro.product.model', '24018RPACC'), @('getprop ro.product.marketname', 'Xiaomi Pad 6S Pro 12.4'),
    @('getprop ro.build.characteristics', 'tablet'), @('getenforce', 'Enforcing'),
    @('settings get secure adaptive_sleep', '1'), @('settings get system screen_off_timeout', '15000'))) {
    if ((Invoke-Adb @('shell', $condition[0])).Trim() -ne $condition[1]) { throw "Preserved state differs: $($condition[0])" }
}
$aon = Save-Shell 'aon-link.txt' 'readlink /vendor/lib64/camera/aon_front.pb; sha256sum /vendor/lib64/camera/aon_front.pb /odm/lib64/camera/aon_front.pb'
if ($aon -notmatch '(?m)^/odm/lib64/camera/aon_front.pb\s*$' -or
    @([regex]::Matches($aon, 'b0d920c16e4968173cf8f4f90c1056e959b9aad1c2651a76cca17ee19dac46d6')).Count -ne 2) {
    throw 'AON alias or unchanged target differs.'
}
$paths = @()
foreach ($partition in @('odm', 'vendor')) {
    foreach ($property in $manifest.frozen_spec.partitions.$partition.files.PSObject.Properties) {
        $paths += '/' + $partition + '/' + $property.Name
    }
}
$libraries = Save-Shell 'reviewed-library-hashes.txt' ('sha256sum ' + ($paths -join ' '))
foreach ($partition in @('odm', 'vendor')) {
    foreach ($property in $manifest.frozen_spec.partitions.$partition.files.PSObject.Properties) {
        if ($libraries -notmatch ('(?m)^' + $property.Value.sha256 + '\s')) { throw "Unreviewed live library: $($property.Name)" }
    }
}
$providers = Save-Shell 'unchanged-provider-hashes.txt' 'sha256sum /vendor/lib64/libui.so /vendor/lib64/libgui_vendor.so /system_ext/priv-app/SystemUI/SystemUI.apk'
foreach ($digest in @('5d6f48b97bbcbf79ce805f96e7d7043597154dbd8c615a8a4dfcaf8b916bf3f1',
    '0b082826f4787ea3332e282e7c9de877c4e7384d388bdb68fdb7fbcdf0b231c3',
    'd2fcdb478e16a259db35bfafe30d0f4e73d3dc96dfe297be601de24f8604c75d')) {
    if ($providers -notmatch ('(?m)^' + $digest + '\s')) { throw 'An unchanged ABI provider or SystemUI differs.' }
}
function Get-ProcessIdentity([string]$tag) {
    $text = Save-Shell ($tag + '.txt') 'for p in $(pidof com.android.systemui vendor.qti.camera.provider-service_64 dolbycodec2 vendor.dolby.media.c2@1.0-service); do cat /proc/$p/stat; done'
    $samples = @{}
    foreach ($line in ($text -split "`n")) {
        if ($line -match '^(\d+) \(.+\) (.+)$') {
            $fields = $Matches[2] -split ' '
            $samples[$Matches[1]] = [long]$fields[11] + [long]$fields[12]
        }
    }
    if ($samples.Count -ne 4) { throw 'Expected SystemUI, camera provider and both Dolby processes.' }
    return $samples
}
$before = Get-ProcessIdentity 'processes-before'
$codecPids = (Invoke-Adb @('shell', 'pidof dolbycodec2 vendor.dolby.media.c2@1.0-service')).Trim() -split '\s+'
$probe = Join-Path $workspace 'reports/device/r25-investigation/sheng-graphicbuffer-abi-probe-client'
$probeDigest = (Get-FileHash -LiteralPath $probe -Algorithm SHA256).Hash.ToLowerInvariant()
if ($probeDigest -ne $review.graphicbuffer_probe_sha256) { throw 'Unreviewed isolated buffer probe.' }
$remote = '/data/local/tmp/sheng-graphicbuffer-abi-r25-final'
$native = '/data/local/tmp/sheng-codec2-hal-r25'
$java = '/data/local/tmp/sheng-codec2-mediacodec-r25.jar'
if ((Invoke-Adb @('shell', "test ! -e $remote && test ! -e $native && test ! -e $java; echo `$?")).Trim() -ne '0') {
    throw 'Temporary probe path already exists.'
}
try {
    Invoke-Adb @('push', $probe, $remote) | Out-Null
    Invoke-Adb @('push', (Join-Path $workspace 'artifacts/audio-diagnostics-sheng/sheng-codec2-hal-probe-r23'), $native) | Out-Null
    Invoke-Adb @('push', (Join-Path $workspace 'artifacts/audio-diagnostics-sheng/sheng-codec2-audio-probe-r23.jar'), $java) | Out-Null
    Invoke-Adb @('shell', "chmod 700 $remote $native") | Out-Null
    $buffer = Save-Shell 'graphicbuffer-client-probe.txt' "timeout 30 env LD_LIBRARY_PATH=/vendor/lib64:/system/lib64 $remote /odm/lib64/libcom.xiaomi.grallocutils.so"
    if ($buffer -notmatch 'graphic_buffer_bytes=3376' -or
        $buffer -notmatch 'candidate_gralloc_client_allocation_release_cycles=100 offscreen_only=true') {
        throw 'Current-sized storage or actual gralloc helper cycles did not finish.'
    }
    $hal = Save-Shell 'hal-probe.txt' "timeout 30 env LD_LIBRARY_PATH=/vendor/lib64:/system/lib64 $native"
    if ($hal -notmatch 'Both Dolby stores passed listComponents and createInterface\.') { throw 'HAL interface checks did not finish.' }
    $media = Save-Shell 'mediacodec-all-components.txt' "timeout 45 env CLASSPATH=$java app_process /system/bin ShengCodec2Probe"
    if ($media -notmatch '(?m)^dolby_components=7 allocated=6\s*$' -or
        $media -notmatch '(?m)^allocated=c2\.dolby\.encoder\.hevc\s*$' -or
        $media -notmatch '(?m)^allocated=c2\.dolby\.decoder\.hevc\s*$') { throw 'MediaCodec lifecycle coverage did not finish.' }
} finally {
    Invoke-Adb @('shell', "rm -f $remote $native $java") | Out-Null
}
$after = Get-ProcessIdentity 'processes-after'
Start-Sleep -Seconds 5
$idle = Get-ProcessIdentity 'processes-after-idle'
foreach ($processId in $before.Keys) {
    if (-not $after.ContainsKey($processId) -or -not $idle.ContainsKey($processId)) { throw 'A monitored process restarted.' }
}
$deltas = @{}
foreach ($processId in $codecPids) {
    $deltas[$processId] = $idle[$processId] - $after[$processId]
    if ($deltas[$processId] -gt 5 -or $deltas[$processId] -lt 0) { throw 'A Dolby service remained busy after release.' }
}
$crashes = Save-Shell 'crash-buffer.txt' 'logcat -b crash -d'
Save-Shell 'startup-logcat.txt' 'logcat -b all -d' | Out-Null
if ($crashes -match 'Process: com\.android\.systemui, PID:|Cmdline: com\.android\.systemui\s|Cmdline: /odm/bin/hw/vendor\.qti\.camera\.provider-service_64|Cmdline: /vendor/bin/hw/(dolbycodec2|vendor\.dolby\.media\.c2@1\.0-service)') {
    throw 'Current boot contains a monitored process crash.'
}
$result = [ordered]@{
    revision=25; serial=$serial; slot='b'; hardware_boot_tested=$true
    installed_partition_hashes=$expected; all_six_partition_hashes_match=$true
    reviewed_seven_libraries_installed=$true; graphic_buffer_bytes=3376
    redzone_construction_destruction_cycles=200; gralloc_client_allocation_release_cycles=100
    media_codec_allocation_count=6; dolby_idle_cpu_ticks_5_seconds=$deltas
    monitored_processes_stable=$true; aon_alias_verified=$true; temporary_probes_cleaned=$true
    camera_preview_user_passed=$null; video_stream_decode_verified=$false
    power_button_animation_user_passed=$null; agent_started_camera_or_attention=$false
    other_connected_device_operated=$false; evidence_directory=$evidence
}
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidence 'runtime-result.json') -Encoding utf8
Write-Output $evidence
