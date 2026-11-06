#requires -Version 7.0
param(
    [Parameter(Mandatory)][string]$ImagePath,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedSha256,
    [string]$Serial = 'ca10ede3'
)
$ErrorActionPreference = 'Stop'
$taskWorkspace = Split-Path -Parent $PSScriptRoot
$taskFastboot = Join-Path $taskWorkspace 'tools\platform-tools\fastboot.exe'
$taskImage = (Resolve-Path -LiteralPath $ImagePath).Path
$taskHash = (Get-FileHash -LiteralPath $taskImage -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskHash -ne $ExpectedSha256.ToLowerInvariant()) { throw 'Image SHA mismatch' }
if ((Get-Item -LiteralPath $taskImage).Length -ne 104857600) { throw 'Expected a 100 MiB sheng Recovery image' }
function Read-TaskVar([string]$Name) {
    $taskLines = & $taskFastboot -s $Serial getvar $Name 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Failed to read $Name" }
    $taskPattern = '(?m)^' + [regex]::Escape($Name) + ':\s*(\S+)'
    $taskMatch = [regex]::Match(($taskLines -join "`n"), $taskPattern)
    if (-not $taskMatch.Success) { throw "Missing value for $Name" }
    return $taskMatch.Groups[1].Value
}
if ((Read-TaskVar 'product') -ne 'sheng') { throw 'Unexpected product' }
if ((Read-TaskVar 'unlocked') -ne 'yes') { throw 'Device locked' }
if ((Read-TaskVar 'is-userspace') -ne 'no') { throw 'Bootloader Fastboot required' }
$taskSlot = Read-TaskVar 'current-slot'
if ($taskSlot -notin @('a', 'b')) { throw 'Unknown active slot' }
$taskPartition = 'recovery_' + $taskSlot
$taskSize = Read-TaskVar ('partition-size:' + $taskPartition)
if ([Convert]::ToInt64(($taskSize -replace '^0x', ''), 16) -ne 104857600) { throw 'Unexpected partition size' }
$taskDir = Join-Path $taskWorkspace ('reports\device\flash-recovery-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $taskDir | Out-Null
$taskResult = @{serial=$Serial; partition=$taskPartition; image=$taskImage; sha256=$taskHash; time=(Get-Date -Format o)}
$taskOutput = & $taskFastboot -s $Serial flash $taskPartition $taskImage 2>&1
$taskResult.flash_exit_code = $LASTEXITCODE
$taskOutput | Tee-Object -FilePath (Join-Path $taskDir 'flash.txt')
$taskResult | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskDir 'flash-result.json') -Encoding utf8
if ($taskResult.flash_exit_code -ne 0) { throw 'Recovery flash failed; not rebooting' }
$taskOutput = & $taskFastboot -s $Serial reboot recovery 2>&1
$taskResult.reboot_exit_code = $LASTEXITCODE
$taskOutput | Tee-Object -FilePath (Join-Path $taskDir 'reboot.txt')
$taskResult | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskDir 'flash-result.json') -Encoding utf8
if ($taskResult.reboot_exit_code -ne 0) { throw 'Reboot to Recovery failed' }
Write-Output "report=$taskDir"
