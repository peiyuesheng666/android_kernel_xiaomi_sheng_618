param([switch]$Run)
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$serial = 'ca10ede3'
$fixtureDir = Join-Path $workspace 'reports/device/video-decode-fixtures-20261108'
$probeDir = Join-Path $workspace 'reports/device/video-decode-probe-20261108'
$probe = Join-Path $probeDir 'sheng-video-decode-probe.jar'
$build = Get-Content -Raw -LiteralPath (Join-Path $probeDir 'build-result.json') | ConvertFrom-Json
$source = Join-Path $PSScriptRoot 'ShengVideoDecodeProbe.java'
function Get-Sha([string]$path) { return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
if ($build.build_passed -ne $true -or (Get-Sha $source) -ne $build.source_sha256 -or
    (Get-Sha $probe) -ne $build.jar_sha256) { throw 'Probe does not match its successful compilation.' }
$fixtures = [ordered]@{
    'glass-blowing2-dolby-vision-profile-5-frag.mp4' = 'd21fc3938a813b6ce25efe890074b23d966a5828c9a3d33de7e8591a25dd2036'
    'glass-blowing2-dolby-vision-profile-8-1-frag.mp4' = '2cbedc36cf1ec2fdaaa54d26942ff93faeda4d4b2baf9fd25ee74bfebc15287e'
}
foreach ($name in $fixtures.Keys) {
    if ((Get-Sha (Join-Path $fixtureDir $name)) -ne $fixtures[$name]) { throw "Unreviewed media fixture: $name" }
}
Write-Output 'Compiled decode probe and both pinned Dolby Vision fixtures verified locally.'
if (-not $Run) { return }
$adb = Join-Path $workspace 'tools/platform-tools/adb.exe'
$evidence = Join-Path $workspace ('reports/device/video-decode-runtime-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
    if (-not $process.WaitForExit(130000)) { $process.Kill(); throw 'Target decode command timed out.' }
    $output = $stdout.Result + "`n" + $stderr.Result
    $exitCode = $process.ExitCode
    $process.Dispose()
    Add-Content -LiteralPath (Join-Path $evidence 'commands.txt') -Value $output -Encoding utf8
    if ($exitCode -ne 0) { throw $output }
    return $output
}
foreach ($condition in @(@('ro.product.device','sheng'), @('ro.boot.slot_suffix','_b'), @('sys.boot_completed','1'))) {
    if ((Invoke-Adb @('shell', ('getprop ' + $condition[0]))).Trim() -ne $condition[1]) { throw 'Wrong target, slot or incomplete boot.' }
}
$review = Get-Content -Raw -LiteralPath (Join-Path $workspace 'device/xiaomi/sheng/docs/build-r25-graphicbuffer-20261108.json') | ConvertFrom-Json
if ($review.revision -ne 25 -or $review.build_passed -ne $true -or $review.allocation_sites -ne 14) { throw 'Missing r25 ABI review.' }
foreach ($partition in @('odm', 'vendor')) {
    foreach ($property in $review.reviewed_sha256.$partition.PSObject.Properties) {
        $hash = Invoke-Adb @('shell', ('sha256sum /' + $partition + '/' + $property.Name))
        if ($hash -notmatch ('(?m)^' + $property.Value + '\s')) { throw 'Install and verify r25 before exercising video buffers.' }
    }
}
foreach ($property in $review.dependency_library_sha256.PSObject.Properties) {
    $hash = Invoke-Adb @('shell', ('sha256sum /vendor/' + $property.Name))
    if ($hash -notmatch ('(?m)^' + $property.Value + '\s')) { throw 'Unexpected ABI provider.' }
}
$processCommand = 'pidof com.android.systemui vendor.qti.camera.provider-service_64 dolbycodec2 vendor.dolby.media.c2@1.0-service'
$before = ((Invoke-Adb @('shell', $processCommand)).Trim() -split '\s+' | Sort-Object) -join ','
if (($before -split ',').Count -ne 4) { throw 'Expected four monitored processes.' }
$remoteJar = '/data/local/tmp/sheng-video-decode-probe-20261108.jar'
$remoteFixture = '/data/local/tmp/sheng-video-decode-fixture-20261108.mp4'
if ((Invoke-Adb @('shell', "test ! -e $remoteJar && test ! -e $remoteFixture; echo `$?")).Trim() -ne '0') {
    throw 'Temporary diagnostic paths already exist.'
}
$passed = @()
try {
    Invoke-Adb @('push', $probe, $remoteJar) | Out-Null
    foreach ($name in $fixtures.Keys) {
        # Each previous fixture is removed before the next one is copied.
        Invoke-Adb @('push', (Join-Path $fixtureDir $name), $remoteFixture) | Out-Null
        try {
            $command = "timeout -s KILL 115 env CLASSPATH=$remoteJar app_process /system/bin ShengVideoDecodeProbe $remoteFixture $($fixtures[$name]) c2.dolby.decoder.hevc"
            $output = Invoke-Adb @('shell', $command)
            Set-Content -LiteralPath (Join-Path $evidence ($name + '.txt')) -Value $output -Encoding utf8
            if ($output -notmatch '(?m)^decode_sessions=2 frames_per_session=([1-9][0-9]*) offscreen_only=true camera_used=false drm_tested=false\s*$') {
                throw 'Two sessions did not finish decoding and draining.'
            }
            $frames = [int]$Matches[1]
            if ($frames -lt 8 -or $frames -gt 60) { throw 'Unexpected decoded frame count.' }
            $passed += [ordered]@{ fixture=$name; sha256=$fixtures[$name]; sessions=2; frames_per_session=$frames }
        } finally { Invoke-Adb @('shell', "rm -f $remoteFixture") | Out-Null }
    }
} finally { Invoke-Adb @('shell', "rm -f $remoteJar $remoteFixture") | Out-Null }
$after = ((Invoke-Adb @('shell', $processCommand)).Trim() -split '\s+' | Sort-Object) -join ','
if ($before -ne $after) { throw 'A monitored process restarted during decoding.' }
$crashes = Invoke-Adb @('shell', 'logcat -b crash -d')
Set-Content -LiteralPath (Join-Path $evidence 'crash-buffer.txt') -Value $crashes -Encoding utf8
if ($crashes -match 'Cmdline: /vendor/bin/hw/(dolbycodec2|vendor\.dolby\.media\.c2@1\.0-service)|Cmdline: /odm/bin/hw/vendor\.qti\.camera\.provider-service_64|Process: com\.android\.systemui, PID:') {
    throw 'A monitored process has crashed in the current boot.'
}
[ordered]@{
    serial=$serial; slot='b'; offscreen_clear_decode_verified=$true; fixtures=$passed
    monitored_processes_stable=$true; agent_executed_adb_root=$false
    camera_used=$false; displayed_or_saved_decoded_frames=$false; drm_tested=$false
    hdr_color_accuracy_verified=$false; encoder_stream_verified=$false
    temporary_probes_cleaned=$true; other_device_operated=$false
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidence 'runtime-result.json') -Encoding utf8
Write-Output $evidence
