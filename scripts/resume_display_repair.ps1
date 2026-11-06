param([int]$WaitHours = 12)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$fastbootPath = Join-Path $workspace 'tools/platform-tools/fastboot.exe'
$adbPath = Join-Path $workspace 'tools/platform-tools/adb.exe'
$imagePath = Join-Path $workspace 'artifacts/system-display-fix-sheng-lineage-24.0-r1/vbmeta-chain-fixed.img'
$logPath = Join-Path $workspace 'reports/device/system-boot-fix-r1-20261106-073514/resume-display-repair.txt'
$expectedHash = 'F0A9D448F68EE32A09E3597750089E4C8334F23B4CC42A977EE72768FDD76ED5'
$serial = 'ca10ede3'

function Write-RepairLog([string]$message) {
    Add-Content -LiteralPath $logPath -Value ('{0:o} {1}' -f (Get-Date), $message) -Encoding UTF8
}

function Invoke-BoundedTool([string]$executable, [string[]]$toolArguments) {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $executable
    $info.Arguments = ($toolArguments | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' }) -join ' '
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    if (-not $process.Start()) { throw 'Could not start platform tool' }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(20000)) {
        $process.Kill()
        throw 'Platform tool timed out'
    }
    $result = $stdout.Result + $stderr.Result
    if ($process.ExitCode -ne 0) { throw $result }
    return $result
}

$sha256 = [System.Security.Cryptography.SHA256]::Create()
$imageHash = [BitConverter]::ToString($sha256.ComputeHash([System.IO.File]::ReadAllBytes($imagePath))).Replace('-', '')
$sha256.Dispose()
if ($imageHash -ne $expectedHash) {
    throw 'Corrected vbmeta hash does not match'
}
Write-RepairLog 'Waiting for this sheng device in Fastboot; no camera or microphone is opened.'
$deadline = (Get-Date).AddHours($WaitHours)
while ((Get-Date) -lt $deadline) {
    $adbDevices = Invoke-BoundedTool $adbPath @('devices')
    if ($adbDevices -match '(?im)^ca10ede3\s+device\s*$') {
        $deviceName = Invoke-BoundedTool $adbPath @('-s', $serial, 'shell', 'getprop', 'ro.product.device')
        $deviceSlot = Invoke-BoundedTool $adbPath @('-s', $serial, 'shell', 'getprop', 'ro.boot.slot_suffix')
        if ($deviceName.Trim() -eq 'sheng' -and $deviceSlot.Trim() -eq '_b') {
            Write-RepairLog 'The verified sheng b-slot ADB endpoint returned; requesting Bootloader for vbmeta repair.'
            Write-RepairLog (Invoke-BoundedTool $adbPath @('-s', $serial, 'reboot', 'bootloader'))
            Start-Sleep -Seconds 10
        }
    }
    $devices = Invoke-BoundedTool $fastbootPath @('devices')
    if ($devices -match '(?im)^ca10ede3\s+fastboot\s*$') {
        $product = Invoke-BoundedTool $fastbootPath @('-s', $serial, 'getvar', 'product')
        $slot = Invoke-BoundedTool $fastbootPath @('-s', $serial, 'getvar', 'current-slot')
        if ($product -notmatch '(?m)^product:\s*sheng\s*$' -or $slot -notmatch '(?m)^current-slot:\s*b\s*$') {
            Write-RepairLog ('Device or slot mismatch; stopped. ' + $product + $slot)
            exit 2
        }
        Write-RepairLog 'Verified ca10ede3, product sheng, slot b. Repairing only vbmeta_b.'
        Write-RepairLog (Invoke-BoundedTool $fastbootPath @('-s', $serial, 'flash', 'vbmeta_b', $imagePath))
        Write-RepairLog (Invoke-BoundedTool $fastbootPath @('-s', $serial, 'reboot'))
        $bootDeadline = (Get-Date).AddMinutes(10)
        while ((Get-Date) -lt $bootDeadline) {
            $adbDevices = Invoke-BoundedTool $adbPath @('devices')
            if ($adbDevices -match '(?im)^ca10ede3\s+device\s*$') {
                $boot = Invoke-BoundedTool $adbPath @('-s', $serial, 'shell', 'getprop', 'sys.boot_completed')
                if ($boot.Trim() -eq '1') {
                    Write-RepairLog 'ADB returned and sys.boot_completed=1. Further hardware validation is still required.'
                    $evidenceDirectory = Split-Path -Parent $logPath
                    foreach ($probe in @(
                        @('post-chain-repair-properties.txt', 'getprop; getenforce; id'),
                        @('post-chain-repair-surfaceflinger.txt', 'timeout 8 dumpsys SurfaceFlinger'),
                        @('post-chain-repair-logcat.txt', 'logcat -d -t 5000'),
                        @('post-chain-repair-audio.txt', 'timeout 8 dumpsys media.audio_flinger; timeout 8 dumpsys audio')
                    )) {
                        try {
                            $evidence = Invoke-BoundedTool $adbPath @('-s', $serial, 'shell', $probe[1])
                            [System.IO.File]::WriteAllText((Join-Path $evidenceDirectory $probe[0]), $evidence)
                        } catch {
                            Write-RepairLog ('Evidence probe failed: ' + $_.Exception.Message)
                        }
                    }
                    try {
                        $mixerProbe = Join-Path $workspace 'artifacts/audio-diagnostics-sheng/tinymix'
                        $probeHasher = [System.Security.Cryptography.SHA256]::Create()
                        $probeHash = [BitConverter]::ToString($probeHasher.ComputeHash([System.IO.File]::ReadAllBytes($mixerProbe))).Replace('-', '')
                        $probeHasher.Dispose()
                        if ($probeHash -ne '1EFF7FC0FA957570760573FCF1C69F73503EFE379C04798ABB7553BB51BEDA55') {
                            throw 'Mixer probe hash changed'
                        }
                        Write-RepairLog (Invoke-BoundedTool $adbPath @('-s', $serial, 'root'))
                        Start-Sleep -Seconds 3
                        Write-RepairLog (Invoke-BoundedTool $adbPath @('-s', $serial, 'push', $mixerProbe, '/data/local/tmp/sheng-tinymix'))
                        $mixerListing = Invoke-BoundedTool $adbPath @('-s', $serial, 'shell', 'chmod 0755 /data/local/tmp/sheng-tinymix; timeout 8 /data/local/tmp/sheng-tinymix -D 100')
                        [System.IO.File]::WriteAllText((Join-Path $evidenceDirectory 'post-chain-repair-mixer100.txt'), $mixerListing)
                    } catch {
                        Write-RepairLog ('Read-only mixer audit failed: ' + $_.Exception.Message)
                    }
                    Write-RepairLog 'Repair evidence saved. Camera capture disabled by the user.'
                    exit 0
                }
            }
            Start-Sleep -Seconds 10
        }
        Write-RepairLog 'vbmeta repair written; boot completion was not confirmed within ten minutes.'
        exit 3
    }
    Start-Sleep -Seconds 20
}
Write-RepairLog 'Wait expired without a Fastboot endpoint; no partition was written.'
exit 4
