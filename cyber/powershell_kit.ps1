<#
.SYNOPSIS
FRIDAY PowerShell Security Toolkit
.DESCRIPTION
Lightweight security tools for bug bounty & pentesting.
All functions return JSON for easy parsing by FRIDAY.
Compatible with PowerShell 5.1+ (no -AsHashtable dependency).
#>

# ── Input Validation Helper ────────────────────────────────────────

function Test-SafeTarget {
    param([string]$Target)
    if ([string]::IsNullOrWhiteSpace($Target)) { return $false }

    $t = $Target.ToLower().Trim()

    # Block localhost variants
    $blockedHosts = @('localhost','0.0.0.0','::1')
    foreach ($h in $blockedHosts) {
        if ($t -eq $h -or $t.StartsWith("$h/") -or $t.StartsWith("$h`:")) { return $false }
    }

    # Block private IP ranges using regex (not substring match)
    if ($t -match '^127\.\d{1,3}\.\d{1,3}\.\d{1,3}') { return $false }
    if ($t -match '^10\.\d{1,3}\.\d{1,3}\.\d{1,3}') { return $false }
    if ($t -match '^192\.168\.\d{1,3}\.\d{1,3}') { return $false }
    if ($t -match '^172\.(1[6-9]|2[0-9]|3[01])\.\d{1,3}\.\d{1,3}') { return $false }
    if ($t -match '^169\.254\.\d{1,3}\.\d{1,3}') { return $false }

    # Also check URLs — extract hostname
    if ($t -match '^https?://([^/:]+)') {
        $hostname = $Matches[1].ToLower()
        if ($hostname -eq 'localhost' -or $hostname -eq '127.0.0.1' -or $hostname -eq '::1') { return $false }
        if ($hostname -match '^127\.' -or $hostname -match '^10\.') { return $false }
        if ($hostname -match '^192\.168\.' -or $hostname -match '^169\.254\.') { return $false }
        if ($hostname -match '^172\.(1[6-9]|2[0-9]|3[01])\.') { return $false }
        if ($hostname -eq '169.254.169.254' -or $hostname -eq 'metadata.google.internal') { return $false }
    }

    return $true
}

# ── Functions ──────────────────────────────────────────────────────

function Invoke-WebRequestEx {
    param(
        [string]$Url,
        [string]$Method = "GET",
        [string]$Headers = "{}",
        [string]$Body = "",
        [int]$Timeout = 30
    )

    # [#1] Validate URL
    if ([string]::IsNullOrWhiteSpace($Url)) {
        [PSCustomObject]@{error="URL is empty";status_code=0} | ConvertTo-Json -Compress
        return
    }
    if ($Url.Length -gt 2048) {
        [PSCustomObject]@{error="URL too long (max 2048 chars)";status_code=0} | ConvertTo-Json -Compress
        return
    }

    $h = @{}
    try { $h = $Headers | ConvertFrom-Json } catch {}

    $params = @{
        Uri             = $Url
        Method          = $Method
        UseBasicParsing = $true
        TimeoutSec      = [Math]::Max(1, [Math]::Min($Timeout, 120))  # [#2]
    }
    if ($h -and $h.PSObject.Properties.Count -gt 0) {
        $hdrTable = @{}
        $h.PSObject.Properties | ForEach-Object { $hdrTable[$_.Name] = $_.Value }
        $params.Headers = $hdrTable
    }
    if ($Body -and ($Method -in @("POST","PUT","PATCH"))) {
        $params.Body = $Body
    }

    try {
        $r = Invoke-WebRequest @params
        $bodyText = if ($r.Content) {
            $r.Content.Substring(0, [Math]::Min($r.Content.Length, 5000))
        } else { "" }

        $hdrOut = @{}
        if ($r.Headers) {
            foreach ($key in $r.Headers.Keys) {
                $val = $r.Headers[$key]
                $hdrOut[$key] = if ($val -is [array]) { $val -join ', ' } else { [string]$val }
            }
        }

        [PSCustomObject]@{
            status_code     = [int]$r.StatusCode
            headers         = $hdrOut
            body            = $bodyText
            content_length  = $r.RawContentLength
        } | ConvertTo-Json -Compress -Depth 3
    } catch {
        $sc = 0
        try { $sc = [int]$_.Exception.Response.StatusCode.value__ } catch {}
        [PSCustomObject]@{
            error       = $_.Exception.Message
            status_code = $sc
        } | ConvertTo-Json -Compress
    }
}

function Invoke-PortScan {
    param(
        [string]$Hostname,
        [string]$Ports = "21,22,23,25,53,80,110,143,443,445,993,995,1433,1521,2049,2375,3306,3389,5432,5900,6379,8080,8443,9000,27017",
        [int]$TimeoutMs = 1000
    )

    # [#3] Validate hostname
    if ([string]::IsNullOrWhiteSpace($Hostname)) {
        [PSCustomObject]@{error="Hostname is empty"} | ConvertTo-Json -Compress
        return
    }
    if (-not (Test-SafeTarget $Hostname)) {
        [PSCustomObject]@{error="Target blocked (private/localhost)"} | ConvertTo-Json -Compress
        return
    }

    $openPorts = @()
    $closedPorts = @()
    $portArray = $Ports -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '^\d+$' }

    # [#4] Validate port count
    if ($portArray.Count -gt 500) {
        [PSCustomObject]@{error="Too many ports (max 500)"} | ConvertTo-Json -Compress
        return
    }

    foreach ($port in $portArray) {
        $portNum = [int]$port
        if ($portNum -lt 1 -or $portNum -gt 65535) { continue }  # [#5]
        $tcp = $null
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $connect = $tcp.BeginConnect($Hostname, $portNum, $null, $null)
            $waited = $connect.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
            if ($waited -and $tcp.Connected) {
                $openPorts += $portNum
                try { $tcp.EndConnect($connect) } catch {}
            } else {
                $closedPorts += $portNum
            }
        } catch {
            $closedPorts += $portNum
        } finally {
            if ($tcp) { try { $tcp.Close() } catch {} }  # [#6]
        }
    }

    $closedSample = if ($closedPorts.Count -gt 20) {
        $closedPorts[0..19]
    } else { $closedPorts }

    [PSCustomObject]@{
        hostname     = $Hostname
        open_ports   = $openPorts
        closed_ports = $closedSample
        total_scanned = $portArray.Count
        open_count   = $openPorts.Count
    } | ConvertTo-Json -Compress
}

function Get-DNSInfo {
    param([string]$Domain)

    if ([string]::IsNullOrWhiteSpace($Domain)) {
        [PSCustomObject]@{error="Domain is empty"} | ConvertTo-Json -Compress
        return
    }
    if (-not (Test-SafeTarget $Domain)) {
        [PSCustomObject]@{error="Target blocked (private/localhost)"} | ConvertTo-Json -Compress
        return
    }

    $results = @{}
    $results.domain = $Domain

    try {
        $aRecords = Resolve-DnsName $Domain -Type A -ErrorAction Stop
        $results.a_records = ($aRecords | Select-Object -ExpandProperty IPAddress) -join ', '
    } catch { $results.a_records = $null }

    try {
        $aaaaRecords = Resolve-DnsName $Domain -Type AAAA -ErrorAction Stop
        $results.aaaa_records = ($aaaaRecords | Select-Object -ExpandProperty IPAddress) -join ', '
    } catch { $results.aaaa_records = $null }

    try {
        $nsRecords = Resolve-DnsName $Domain -Type NS -ErrorAction Stop
        $results.ns_records = ($nsRecords | Select-Object -ExpandProperty NameHost) -join ', '
    } catch { $results.ns_records = $null }

    try {
        $mxRecords = Resolve-DnsName $Domain -Type MX -ErrorAction Stop
        $results.mx_records = ($mxRecords | ForEach-Object {
            "$($_.NameExchange) (priority: $($_.Preference))"
        }) -join ', '
    } catch { $results.mx_records = $null }

    try {
        $txtRecords = Resolve-DnsName $Domain -Type TXT -ErrorAction Stop
        $results.txt_records = ($txtRecords | Select-Object -First 10 -ExpandProperty Strings) -join ' | '
    } catch { $results.txt_records = $null }

    try {
        $cnameRecord = Resolve-DnsName $Domain -Type CNAME -ErrorAction Stop
        $results.cname = ($cnameRecord | Select-Object -First 1 -ExpandProperty NameHost)
    } catch { $results.cname = $null }

    try {
        $soaRecord = Resolve-DnsName $Domain -Type SOA -ErrorAction Stop
        $results.soa = "$($soaRecord.NameAdministrator) serial:$($soaRecord.SerialNumber)"
    } catch { $results.soa = $null }

    $results | ConvertTo-Json -Compress
}

function Invoke-SSLInfo {
    param([string]$Hostname, [int]$Port = 443)

    if ([string]::IsNullOrWhiteSpace($Hostname)) {
        [PSCustomObject]@{error="Hostname is empty"} | ConvertTo-Json -Compress
        return
    }
    if (-not (Test-SafeTarget $Hostname)) {
        [PSCustomObject]@{error="Target blocked (private/localhost)"} | ConvertTo-Json -Compress
        return
    }

    $tcp = $null
    $ssl = $null
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect($Hostname, $Port)
        $ssl = New-Object System.Net.Security.SslStream(
            $tcp.GetStream(), $false,
            { param($sender, $cert, $chain, $errors) $true }
        )

        # [#7] Try TLS 1.3 first, fall back to 1.2, then system default
        try {
            $ssl.AuthenticateAsClient($Hostname)
        } catch {
            try {
                $ssl.AuthenticateAsClient($Hostname, $null,
                    [System.Security.Authentication.SslProtocols]::Tls12, $false)
            } catch {
                $ssl.AuthenticateAsClient($Hostname, $null,
                    [System.Security.Authentication.SslProtocols]::Default, $false)
            }
        }

        $cert = $ssl.RemoteCertificate
        if (-not $cert) {
            [PSCustomObject]@{error="No certificate returned"} | ConvertTo-Json -Compress
            return
        }

        $cert2 = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($cert)

        $san = ""
        try {
            $san = ($cert2.Extensions | Where-Object {
                $_.Oid.Value -eq '2.5.29.17'
            } | ForEach-Object { $_.Format($false) }) -join ', '
        } catch {}

        # [#8] Extract all key info
        $sigAlg = ""
        try { $sigAlg = $cert2.SignatureAlgorithm.FriendlyName } catch {}

        [PSCustomObject]@{
            subject          = $cert2.Subject
            issuer           = $cert2.Issuer
            not_before       = $cert2.NotBefore.ToString('yyyy-MM-dd HH:mm:ss')
            expiry           = $cert2.NotAfter.ToString('yyyy-MM-dd HH:mm:ss')
            days_remaining   = [math]::Round(($cert2.NotAfter - (Get-Date)).TotalDays)
            serial           = $cert2.SerialNumber
            thumbprint       = $cert2.Thumbprint
            san              = $san
            signature_algo   = $sigAlg
            key_length       = $cert2.PublicKey.Key.KeySize
            tls_version      = $ssl.SslProtocol.ToString()
            cipher_suite     = $ssl.CipherAlgorithm.ToString()
            is_valid         = ($cert2.NotAfter -gt (Get-Date))
        } | ConvertTo-Json -Compress
    } catch {
        [PSCustomObject]@{error=$_.Exception.Message} | ConvertTo-Json -Compress
    } finally {
        if ($ssl) { try { $ssl.Close() } catch {} }
        if ($tcp) { try { $tcp.Close() } catch {} }
    }
}

function Invoke-WhoisEx {
    param([string]$Domain)

    if ([string]::IsNullOrWhiteSpace($Domain)) {
        [PSCustomObject]@{error="Domain is empty"} | ConvertTo-Json -Compress
        return
    }
    if (-not (Test-SafeTarget $Domain)) {
        [PSCustomObject]@{error="Target blocked (private/localhost)"} | ConvertTo-Json -Compress
        return
    }

    $sock = $null
    try {
        $sock = New-Object System.Net.Sockets.TcpClient
        $sock.Connect("whois.iana.org", 43)
        $sock.ReceiveTimeout = 10000  # [#9]
        $stream = $sock.GetStream()
        $writer = New-Object System.IO.StreamWriter($stream)
        $writer.WriteLine($Domain)
        $writer.Flush()
        $reader = New-Object System.IO.StreamReader($stream)
        $response = $reader.ReadToEnd()

        # [#10] Parse useful fields from whois response
        $registrar = ""
        $creation = ""
        $expiry = ""
        $nameServers = @()

        foreach ($line in ($response -split "`n")) {
            $line = $line.Trim()
            if ($line -match 'registrar:\s*(.+)') { $registrar = $Matches[1].Trim() }
            if ($line -match 'creation-date:\s*(.+)') { $creation = $Matches[1].Trim() }
            if ($line -match 'registrar registration expiration date:\s*(.+)' -or
                $line -match 'expiry-date:\s*(.+)' -or
                $line -match 'Expiration Date:\s*(.+)') { $expiry = $Matches[1].Trim() }
            if ($line -match 'nserver:\s*(.+)') { $nameServers += $Matches[1].Trim() }
            if ($line -match 'Name Server:\s*(.+)') { $nameServers += $Matches[1].Trim() }
        }

        [PSCustomObject]@{
            domain      = $Domain
            registrar   = $registrar
            created     = $creation
            expires     = $expiry
            name_servers = ($nameServers | Select-Object -Unique) -join ', '
            raw         = $response.Substring(0, [Math]::Min($response.Length, 3000))
        } | ConvertTo-Json -Compress
    } catch {
        [PSCustomObject]@{error=$_.Exception.Message} | ConvertTo-Json -Compress
    } finally {
        if ($sock) { try { $sock.Close() } catch {} }
    }
}

function Invoke-HTTPFuzzer {
    param(
        [string]$BaseUrl,
        [string]$Wordlist = "admin,api,backup,config,db,dev,git,login,robots.txt,sitemap.xml,test,uploads,wp-admin,.env,.git/config",
        [string]$Extensions = ",.php,.asp,.aspx,.jsp,.bak,.old,.txt,.json,.xml,.zip,.tar.gz,.sql",
        [int]$TimeoutSec = 5,
        [int]$MaxPaths = 500  # [#11]
    )

    if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
        [PSCustomObject]@{error="BaseUrl is empty"} | ConvertTo-Json -Compress
        return
    }
    if (-not (Test-SafeTarget $BaseUrl)) {
        [PSCustomObject]@{error="Target blocked (private/localhost)"} | ConvertTo-Json -Compress
        return
    }

    $paths = $Wordlist -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' }
    $exts = $Extensions -split ',' | ForEach-Object { $_.Trim() }

    # [#12] Calculate total URLs and cap
    $totalUrls = 0
    foreach ($path in $paths) {
        $totalUrls += 1 + ($exts | Where-Object { $_ -ne '' }).Count
    }
    if ($totalUrls -gt $MaxPaths) {
        [PSCustomObject]@{
            error = "Too many URLs to test ($totalUrls, max $MaxPaths). Reduce wordlist or extensions."
        } | ConvertTo-Json -Compress
        return
    }

    $results = @()
    $tested = 0

    foreach ($path in $paths) {
        $urls = @($BaseUrl.TrimEnd('/') + '/' + $path)
        foreach ($ext in $exts) {
            if ($ext -ne '') {
                $urls += $BaseUrl.TrimEnd('/') + '/' + $path + $ext
            }
        }
        foreach ($u in $urls) {
            $tested++
            try {
                $r = Invoke-WebRequest $u -UseBasicParsing -TimeoutSec $TimeoutSec -Method GET -ErrorAction Stop
                if ([int]$r.StatusCode -in @(200, 201, 204, 301, 302, 401, 403)) {
                    $results += [PSCustomObject]@{
                        url    = $u
                        status = [int]$r.StatusCode
                        size   = $r.RawContentLength
                    }
                }
            } catch {
                $sc = 0
                try { $sc = [int]$_.Exception.Response.StatusCode.value__ } catch {}
                if ($sc -in @(401, 403, 301, 302)) {
                    $results += [PSCustomObject]@{
                        url    = $u
                        status = $sc
                        size   = 0
                    }
                }
            }
        }
    }

    if ($results.Count -eq 0) {
        [PSCustomObject]@{
            message      = "No interesting responses found"
            paths_tested = $tested
        } | ConvertTo-Json -Compress
    } else {
        # [#13] Return structured response
        [PSCustomObject]@{
            total_found  = $results.Count
            paths_tested = $tested
            results      = $results
        } | ConvertTo-Json -Compress -Depth 3
    }
}

function Get-HttpArchive {
    param([string]$Domain)

    if ([string]::IsNullOrWhiteSpace($Domain)) {
        [PSCustomObject]@{error="Domain is empty"} | ConvertTo-Json -Compress
        return
    }
    if (-not (Test-SafeTarget $Domain)) {
        [PSCustomObject]@{error="Target blocked (private/localhost)"} | ConvertTo-Json -Compress
        return
    }

    try {
        # [#14] URL encode the domain
        $encodedDomain = [System.Uri]::EscapeDataString("*.$Domain")
        $url = "https://web.archive.org/cdx/search/cdx?url=$encodedDomain&output=json&fl=original,statuscode,mimetype&limit=200&filter=statuscode:200"

        $r = Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 15
        $data = $r.Content | ConvertFrom-Json

        $urls = @()
        $interesting = @()  # [#15] Flag interesting archived paths

        if ($data -and $data.Count -gt 1) {
            $entries = $data | Select-Object -Skip 1
            $urls = $entries | ForEach-Object { $_[0] } | Sort-Object -Unique | Select-Object -First 50

            # Find interesting paths (admin panels, configs, APIs)
            $interestingPatterns = @('.env','.git','admin','backup','config','database',
                                     'debug','dump','export','install','log','phpinfo',
                                     'setup','sql','swagger','test','wp-admin','wp-config')
            foreach ($entry in $entries) {
                $entryUrl = [string]$entry[0]
                foreach ($pattern in $interestingPatterns) {
                    if ($entryUrl -match $pattern) {
                        $interesting += $entryUrl
                        break
                    }
                }
            }
            $interesting = $interesting | Sort-Object -Unique | Select-Object -First 20
        }

        $sample = if ($urls.Count -gt 20) { $urls[0..19] } else { $urls }

        [PSCustomObject]@{
            domain            = $Domain
            urls_found        = $urls.Count
            sample_urls       = $sample
            interesting_paths = $interesting
        } | ConvertTo-Json -Compress -Depth 3
    } catch {
        [PSCustomObject]@{error = $_.Exception.Message} | ConvertTo-Json -Compress
    }
}

function Invoke-HealthCheck {
    [PSCustomObject]@{
        status = "ready"
        tools  = @(
            "Invoke-WebRequestEx",
            "Invoke-PortScan",
            "Get-DNSInfo",
            "Invoke-SSLInfo",
            "Invoke-WhoisEx",
            "Invoke-HTTPFuzzer",
            "Get-HttpArchive"
        )
        ps_version  = $PSVersionTable.PSVersion.ToString()
        os_version  = [System.Environment]::OSVersion.VersionString
        timestamp   = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    } | ConvertTo-Json -Compress
}

# ── Route command ───────────────────────────────────────────────────

$cmd = $args[0]
$params = @{}
if ($args.Length -gt 1 -and $args[1]) {
    try {
        $jsonObj = $args[1] | ConvertFrom-Json
        if ($null -ne $jsonObj) {
            $jsonObj.PSObject.Properties | ForEach-Object {
                $params[$_.Name] = $_.Value
            }
        }
    } catch {
        # JSON parsing failed — continue with empty params
    }
}

switch ($cmd) {
    "health"        { Invoke-HealthCheck }
    "web_request"   { Invoke-WebRequestEx @params }
    "port_scan"     { Invoke-PortScan @params }
    "dns_info"      { Get-DNSInfo @params }
    "ssl_info"      { Invoke-SSLInfo @params }
    "whois"         { Invoke-WhoisEx @params }
    "fuzz"          { Invoke-HTTPFuzzer @params }
    "http_archive"  { Get-HttpArchive @params }
    default         {
        [PSCustomObject]@{error="Unknown command: $cmd"} | ConvertTo-Json -Compress
    }
}
