# Atomically publish one complete sibling directory on Windows; paths are JSON data on stdin.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Get-AbsoluteNativePath([object] $Value) {
    if ($Value -isnot [string] -or $Value -notmatch '^[A-Za-z]:\\' -or $Value.Contains([char]0)) {
        throw 'Publication paths must be absolute native drive paths.'
    }
    $Full = [System.IO.Path]::GetFullPath($Value)
    if (-not [string]::Equals($Value, $Full, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Publication paths must be normalized.'
    }
    return $Full
}

try {
    $Reader = New-Object System.IO.StreamReader([Console]::OpenStandardInput(), [Text.Encoding]::UTF8)
    try { $Request = $Reader.ReadToEnd() | ConvertFrom-Json } finally { $Reader.Dispose() }
    $Names = @($Request.PSObject.Properties.Name)
    if ($Names.Count -ne 2 -or @($Names | Where-Object { $_ -notin @('source', 'destination') }).Count -ne 0) {
        throw 'Only source and destination may be supplied.'
    }
    $Source = Get-AbsoluteNativePath $Request.source
    $Destination = Get-AbsoluteNativePath $Request.destination
    $Parent = [System.IO.Path]::GetDirectoryName($Source)
    if ([string]::IsNullOrEmpty($Parent) -or
        -not [string]::Equals($Parent, [System.IO.Path]::GetDirectoryName($Destination), [StringComparison]::OrdinalIgnoreCase) -or
        [string]::Equals($Source, $Destination, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Source and destination must be distinct siblings.'
    }
    if (-not [System.IO.Directory]::Exists($Source)) { throw 'Source directory is missing.' }
    $Attributes = [System.IO.File]::GetAttributes($Source)
    if (($Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'Source directory must not be a reparse point.'
    }
    # Enumerate names rather than following the destination: dangling reparse points count as existing.
    $TargetName = [System.IO.Path]::GetFileName($Destination)
    foreach ($Entry in [System.IO.Directory]::EnumerateFileSystemEntries($Parent)) {
        if ([string]::Equals([System.IO.Path]::GetFileName($Entry), $TargetName, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Destination already exists.'
        }
    }
    # Directory.Move uses the native, non-overwriting directory operation. A destination created
    # after the check causes this call to fail; it never merges directories or publishes files separately.
    [System.IO.Directory]::Move($Source, $Destination)
    [Console]::Out.WriteLine('{"published":true}')
} catch {
    [Console]::Error.WriteLine($_.Exception.GetBaseException().Message)
    exit 1
}
