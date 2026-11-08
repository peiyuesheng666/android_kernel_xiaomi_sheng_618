# SPDX-License-Identifier: Apache-2.0
param([string]$DeviceSerial = 'ca10ede3', [int]$WaitSeconds = 3)
$ErrorActionPreference = 'Stop'
$taskResults = @{}
function Read-U16([byte[]]$Data, [int]$Offset) {
    return ([int]$Data[$Offset] * 256 + [int]$Data[$Offset + 1])
}
function Read-DnsName([byte[]]$Data, [int]$Offset, [int]$Depth = 0) {
    if($Depth -gt 20) { throw 'DNS pointer recursion' }
    $taskLabels = [Collections.Generic.List[string]]::new()
    $taskCursor = $Offset
    while($taskCursor -lt $Data.Length) {
        $taskLength = [int]$Data[$taskCursor]
        $taskCursor++
        if($taskLength -eq 0) { return @{Name=($taskLabels -join '.'); Next=$taskCursor} }
        if(($taskLength -band 192) -eq 192) {
            $taskPointer = (($taskLength -band 63) * 256) + $Data[$taskCursor]
            $taskPart = Read-DnsName $Data $taskPointer ($Depth+1)
            $taskLabels.Add($taskPart.Name)
            return @{Name=($taskLabels -join '.'); Next=($taskCursor+1)}
        }
        if($taskLength -gt 63 -or $taskCursor+$taskLength -gt $Data.Length) { throw 'Malformed DNS name' }
        $taskLabels.Add([Text.Encoding]::UTF8.GetString($Data, $taskCursor, $taskLength))
        $taskCursor += $taskLength
    }
    throw 'Unterminated DNS name'
}
$taskPacket = [Collections.Generic.List[byte]]::new()
$taskPacket.AddRange([byte[]](0,1,0,0,0,1,0,0,0,0,0,0))
foreach($taskLabel in '_adb-tls-connect._tcp.local'.Split('.')) {
    $taskPacket.Add([byte]$taskLabel.Length)
    $taskPacket.AddRange([Text.Encoding]::ASCII.GetBytes($taskLabel))
}
$taskPacket.AddRange([byte[]](0,0,12,128,1))
$taskAddresses = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.AddressState -eq 'Preferred' -and $_.IPAddress -notmatch '^(127\.|169\.254\.)'
}
foreach($taskAddress in $taskAddresses) {
    $taskUdp = $null
    try {
        $taskLocalIp = [Net.IPAddress]::Parse($taskAddress.IPAddress)
        $taskUdp = [Net.Sockets.UdpClient]::new([Net.IPEndPoint]::new($taskLocalIp,0))
        $taskUdp.Client.ReceiveTimeout = 350
        $taskUdp.Client.SetSocketOption([Net.Sockets.SocketOptionLevel]::IP,
            [Net.Sockets.SocketOptionName]::MulticastInterface,$taskLocalIp.GetAddressBytes())
        $taskUdp.Ttl = 255
        [void]$taskUdp.Send($taskPacket.ToArray(),$taskPacket.Count,'224.0.0.251',5353)
        $taskEnd = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
        while([DateTime]::UtcNow -lt $taskEnd) {
            $taskRemote = [Net.IPEndPoint]::new([Net.IPAddress]::Any,0)
            try { $taskData = $taskUdp.Receive([ref]$taskRemote) } catch [Net.Sockets.SocketException] { continue }
            if($taskData.Length -lt 12) { continue }
            $taskPos = 12
            for($taskQ=0;$taskQ -lt (Read-U16 $taskData 4);$taskQ++) {
                $taskName = Read-DnsName $taskData $taskPos
                $taskPos = $taskName.Next + 4
            }
            while($taskPos + 10 -le $taskData.Length) {
                $taskName = Read-DnsName $taskData $taskPos
                $taskPos = $taskName.Next
                $taskType = Read-U16 $taskData $taskPos
                $taskSize = Read-U16 $taskData ($taskPos+8)
                $taskPos += 10
                if($taskPos+$taskSize -gt $taskData.Length) { break }
                if($taskType -eq 33 -and $taskSize -ge 6 -and
                   $taskName.Name -like "*$DeviceSerial*._adb-tls-connect._tcp.local") {
                    $taskPort = Read-U16 $taskData ($taskPos+4)
                    if($taskPort -gt 0) {
                        $taskEndpoint = $taskRemote.Address.ToString() + ':' + $taskPort
                        $taskResults[$taskEndpoint] = @{endpoint=$taskEndpoint; service=$taskName.Name; local_address=$taskAddress.IPAddress}
                    }
                }
                $taskPos += $taskSize
            }
        }
    } catch { Write-Verbose $_ } finally { if($taskUdp) { $taskUdp.Dispose() } }
}
ConvertTo-Json -Compress -InputObject @($taskResults.Values)
