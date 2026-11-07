# Preserve every artifact path while moving verified generated files off C:.
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../../..')).Path
$source = [IO.Path]::GetFullPath((Join-Path $workspace 'artifacts'))
$backup = [IO.Path]::GetFullPath((Join-Path $workspace 'artifacts.c-drive-backup'))
$destination = 'E:\XiaomiPad6SProPort6.18-artifacts'
if ((Split-Path -Parent $source) -ne $workspace -or
        (Split-Path -Parent $backup) -ne $workspace -or
        $destination -ne [IO.Path]::GetFullPath($destination)) { throw 'Unsafe storage paths.' }
if ((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Artifact storage is already redirected.'
}
if ((Test-Path -LiteralPath $backup) -or (Test-Path -LiteralPath $destination)) {
    throw 'Never overwrite a storage copy or backup.'
}
$sourceEntries = @(Get-ChildItem -LiteralPath $source -Recurse -Force)
if (@($sourceEntries | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
    throw 'Do not copy or remove a tree containing reparse points.'
}
$sourceFiles = @($sourceEntries | Where-Object { -not $_.PSIsContainer })
$bytes = ($sourceFiles | Measure-Object -Property Length -Sum).Sum
if ((Get-PSDrive E).Free -lt ($bytes + 1GB)) { throw 'Insufficient destination space.' }
Write-Output "Copying $($sourceFiles.Count) generated files ($bytes bytes) to E:."
Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
$destinationFiles = @(Get-ChildItem -LiteralPath $destination -File -Recurse -Force)
if ($destinationFiles.Count -ne $sourceFiles.Count) { throw 'Copied file inventory mismatch.' }
$verified = foreach ($file in $sourceFiles) {
    $relative = $file.FullName.Substring($source.Length + 1)
    $target = Join-Path $destination $relative
    $digest = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    if ((Get-Item -LiteralPath $target).Length -ne $file.Length -or
            (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $digest) {
        throw "Artifact copy verification failed: $relative"
    }
    [pscustomobject]@{ path = $relative; bytes = $file.Length; sha256 = $digest }
}
Write-Output 'Every copied file hash matches; switching the artifact directory.'
# Rename first so a failed junction/access check can restore the original tree.
Move-Item -LiteralPath $source -Destination $backup
try {
    New-Item -ItemType Junction -Path $source -Value $destination | Out-Null
    $wslProbe = & wsl -d Ubuntu-22.04 -- bash -lc 'sha256sum /mnt/c/Users/Dev裴月笙/Desktop/XiaomiPad6SProPort6.18/artifacts/system-hardware-followup-sheng-r11/vbmeta.img'
    if ($LASTEXITCODE -ne 0 -or ($wslProbe -join "`n") -notmatch '^43412dea1eebb58489cd8acfec9368123af94090d3b2665aab225abc61f17e78\s') {
        throw 'WSL cannot read the preserved artifact path.'
    }
    foreach ($file in $verified) {
        if ((Get-FileHash -LiteralPath (Join-Path $source $file.path) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
            throw "Redirected file verification failed: $($file.path)"
        }
    }
    # A writer may have added/changed files since the initial copy. Refuse to
    # delete any original data that is absent from the verified destination.
    $backupEntries = @(Get-ChildItem -LiteralPath $backup -Recurse -Force)
    if (@($backupEntries | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
        throw 'Backup unexpectedly contains a reparse point.'
    }
    $backupFiles = @($backupEntries | Where-Object { -not $_.PSIsContainer })
    $backupNames = @($backupFiles | ForEach-Object { $_.FullName.Substring($backup.Length + 1) } | Sort-Object)
    $expectedNames = @($verified.path | Sort-Object)
    if ((Compare-Object $backupNames $expectedNames) -or $backupFiles.Count -ne $verified.Count) {
        throw 'Original artifact inventory changed during the copy.'
    }
    foreach ($file in $verified) {
        $original = Join-Path $backup $file.path
        if ((Get-Item -LiteralPath $original).Length -ne $file.bytes -or
                (Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.sha256) {
            throw "Original artifact changed during the copy: $($file.path)"
        }
    }
} catch {
    if (Test-Path -LiteralPath $source) {
        # Delete the junction itself without traversing its destination.
        [IO.Directory]::Delete($source)
    }
    Move-Item -LiteralPath $backup -Destination $source
    throw
}
# All copy/access verification has passed. Check the final deletion target again.
if ((Resolve-Path -LiteralPath $backup).Path -ne $backup -or
        ((Get-Item -LiteralPath $backup).Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        (Split-Path -Parent $backup) -ne $workspace) { throw 'Unsafe backup removal target.' }
Remove-Item -LiteralPath $backup -Recurse -Force
$result = [ordered]@{ date = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK'); original_path = $source
    destination = $destination; copied_bytes = $bytes; verified_files = $verified
    all_hashes_verified = $true; wsl_original_path_verified = $true
    original_path_preserved_by_junction = $true; redundant_c_drive_copy_deleted = $true
    c_drive_free_bytes_after = (Get-PSDrive C).Free }
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $workspace 'device/xiaomi/sheng/docs/artifact-storage-20261107.json') -Encoding utf8
Write-Output "Artifact relocation complete. C: free bytes: $($result.c_drive_free_bytes_after)"
