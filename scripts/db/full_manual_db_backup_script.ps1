#Requires -Version 5.1
# ======================================================
# Full Manual Database Backup Script (PowerShell)
# ======================================================
# Backs up a PostgreSQL database with pg_dump (two SQL files per run):
#   1. Full backup  — schema + data  ({Project}_db_backup_full_{timestamp}.sql)
#   2. Schema only  — DDL only, no rows ({Project}_db_schema_{timestamp}.sql)
# A paired Markdown summary ({Project}_db_backup_full_{timestamp}.summary.md) is written for the full dump.
# Password is prompted at runtime (not stored in this file). Use .pgpass or peer
# auth with -SkipPasswordPrompt if you do not use a password.
#
# BackupDirectory: use an absolute path, or a path relative to the current working
# directory when you launch the script (e.g. "." or ".\backups").

[CmdletBinding()]
param(
    [Parameter()][string]$ProjectName = 'kaizen',
    [Parameter()][string]$DatabaseName = 'kaizen_dev',
    [Parameter()][string]$UserName = 'postgres',
    [Parameter()][string]$HostName = 'localhost',
    [Parameter()][ValidateRange(1, 65535)][int]$Port = 5432,

    # [Parameter()][string]$ProjectName = 'CAMS',
    # [Parameter()][string]$DatabaseName = 'kaizen',
    # [Parameter()][string]$UserName = 'praveen',
    # [Parameter()][string]$HostName = '13.234.142.190',
    # [Parameter()][ValidateRange(1, 65535)][int]$Port = 5433,
    
    # Relative paths resolve against the current location (Get-Location); absolute paths are used as-is.
    [Parameter()][string]$BackupDirectory = '.',

    # Full path to pg_dump executable if not on PATH (e.g. "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe").
    [Parameter()][string]$PgDumpPath = 'pg_dump',

    # Full path to psql executable if not on PATH. If omitted and PgDumpPath is a full path, the script
    # tries the sibling psql executable in the same PostgreSQL bin folder.
    [Parameter()][string]$PsqlPath = 'psql',

    # Delete matching backups in BackupDirectory older than this many days (0 = disabled). Runs after a successful dump.
    [Parameter()][ValidateRange(0, 3650)][int]$RetentionDays = 0,

    # Do not prompt for password (trust/peer auth or credentials from elsewhere).
    [Parameter()][switch]$SkipPasswordPrompt,

    # Skip the schema-only pg_dump (full backup + summary still run).
    [Parameter()][switch]$SkipSchemaDump
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-BackupDirectory {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        $Path = '.'
    }
    if (-not [System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath((Join-Path -Path (Get-Location).Path -ChildPath $Path))
    }
    return [System.IO.Path]::GetFullPath($Path)
}

function Remove-PgPasswordEnv {
    if (Test-Path Env:PGPASSWORD) {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
}

function Get-OsPlatformInfo {
    $platformWindows = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)
    $platformLinux = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Linux)
    $platformMacOS = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::OSX)

    $family = 'Unknown'
    if ($platformWindows) {
        $family = 'Windows'
    }
    elseif ($platformLinux) {
        $family = 'Linux'
    }
    elseif ($platformMacOS) {
        $family = 'macOS'
    }

    return [pscustomobject]@{
        IsWindows = $platformWindows
        IsLinux   = $platformLinux
        IsMacOS   = $platformMacOS
        Family    = $family
    }
}

function Resolve-PsqlPath {
    param(
        [string]$RequestedPath,
        [string]$PgDumpExecutable
    )

    if (-not [string]::IsNullOrWhiteSpace($RequestedPath) -and $RequestedPath -ne 'psql') {
        return $RequestedPath
    }

    if (-not [string]::IsNullOrWhiteSpace($PgDumpExecutable) -and [System.IO.Path]::IsPathRooted($PgDumpExecutable)) {
        $platform = Get-OsPlatformInfo
        $psqlName = if ($platform.IsWindows) { 'psql.exe' } else { 'psql' }
        $candidate = Join-Path -Path (Split-Path -Path $PgDumpExecutable -Parent) -ChildPath $psqlName
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    return $RequestedPath
}

function Format-FileSize {
    param([long]$Bytes)

    if ($Bytes -lt 1KB) { return "$Bytes B" }
    if ($Bytes -lt 1MB) { return ('{0:N2} KB' -f ($Bytes / 1KB)) }
    if ($Bytes -lt 1GB) { return ('{0:N2} MB' -f ($Bytes / 1MB)) }
    return ('{0:N2} GB' -f ($Bytes / 1GB))
}

function Invoke-PsqlMetricsQuery {
    param(
        [string]$ExecutablePath,
        [string]$Database,
        [string]$User,
        [string]$DbHost,
        [int]$DbPort
    )

    $sql = @"
SELECT 'table_count', COUNT(*)::text
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
  AND table_type = 'BASE TABLE'
UNION ALL
SELECT 'constraint_count', COUNT(*)::text
FROM pg_constraint c
JOIN pg_namespace n ON n.oid = c.connamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
UNION ALL
SELECT 'index_count', COUNT(*)::text
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('i', 'I')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
UNION ALL
SELECT 'view_count', COUNT(*)::text
FROM information_schema.views
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
UNION ALL
SELECT 'function_count', COUNT(*)::text
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
  AND p.prokind IN ('f', 'p')
UNION ALL
SELECT 'trigger_count', COUNT(*)::text
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT t.tgisinternal
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
UNION ALL
SELECT 'estimated_record_count', COALESCE(SUM(n_live_tup), 0)::bigint::text
FROM pg_stat_user_tables
UNION ALL
SELECT 'database_size', pg_size_pretty(pg_database_size(current_database()))
UNION ALL
SELECT 'server_version', current_setting('server_version')
UNION ALL
SELECT 'server_timezone', current_setting('TimeZone')
UNION ALL
SELECT 'server_data_directory', current_setting('data_directory')
UNION ALL
SELECT 'server_addr', COALESCE(inet_server_addr()::text, 'local_socket')
UNION ALL
SELECT 'server_port', COALESCE(inet_server_port()::text, 'N/A')
UNION ALL
SELECT 'client_addr', COALESCE(inet_client_addr()::text, 'local_socket')
UNION ALL
SELECT 'current_db_user', current_user
UNION ALL
SELECT 'postmaster_start_time', to_char(pg_postmaster_start_time(), 'YYYY-MM-DD HH24:MI:SS')
UNION ALL
SELECT 'server_is_in_recovery', pg_is_in_recovery()::text;
"@

    $psqlArgs = @(
        '-h', $DbHost
        '-p', "$DbPort"
        '-U', $User
        '-d', $Database
        '-X'
        '-A'
        '-t'
        '-F', '|'
        '-v', 'ON_ERROR_STOP=1'
        '-c', $sql
    )

    $output = & $ExecutablePath @psqlArgs 2>&1
    $exitCode = $LASTEXITCODE

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output   = @($output)
    }
}

function Get-BackupSummaryData {
    param(
        [string]$RequestedPsqlPath,
        [string]$PgDumpExecutable,
        [string]$Database,
        [string]$User,
        [string]$DbHost,
        [int]$DbPort
    )

    $warnings = New-Object System.Collections.Generic.List[string]
    $metrics = [ordered]@{}
    $resolvedPsqlPath = Resolve-PsqlPath -RequestedPath $RequestedPsqlPath -PgDumpExecutable $PgDumpExecutable

    try {
        $null = Get-Command $resolvedPsqlPath -ErrorAction Stop
    }
    catch {
        $warnings.Add("Metadata summary skipped because psql was not found. Set -PsqlPath if needed.")
        return [pscustomobject]@{
            Metrics          = $metrics
            Warnings         = $warnings
            ResolvedPsqlPath = $resolvedPsqlPath
        }
    }

    $queryResult = Invoke-PsqlMetricsQuery -ExecutablePath $resolvedPsqlPath -Database $Database -User $User -DbHost $DbHost -DbPort $DbPort
    if ($queryResult.ExitCode -ne 0) {
        $details = ($queryResult.Output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 2) -join ' '
        if ([string]::IsNullOrWhiteSpace($details)) {
            $details = 'psql returned a non-zero exit code.'
        }
        $warnings.Add("Metadata summary is partial because the database metrics query failed. $details")
        return [pscustomobject]@{
            Metrics          = $metrics
            Warnings         = $warnings
            ResolvedPsqlPath = $resolvedPsqlPath
        }
    }

    foreach ($line in $queryResult.Output) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $parts = $line -split '\|', 2
        if ($parts.Count -ne 2) {
            continue
        }

        $metrics[$parts[0]] = $parts[1]
    }

    return [pscustomobject]@{
        Metrics          = $metrics
        Warnings         = $warnings
        ResolvedPsqlPath = $resolvedPsqlPath
    }
}

function Get-MetricValueOrDefault {
    param(
        [System.Collections.IDictionary]$Metrics,
        [string]$Key,
        [string]$Default = 'N/A'
    )

    if ($Metrics.Contains($Key) -and -not [string]::IsNullOrWhiteSpace($Metrics[$Key])) {
        return $Metrics[$Key]
    }

    return $Default
}

function Test-IsPrivateIpv4 {
    param([string]$IpAddress)

    if ([string]::IsNullOrWhiteSpace($IpAddress)) {
        return $false
    }

    return ($IpAddress -match '^(10\.|127\.|192\.168\.|169\.254\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)')
}

function Resolve-IPv4FromHostName {
    param([string]$TargetHost)

    $result = New-Object System.Collections.Generic.List[string]
    if ([string]::IsNullOrWhiteSpace($TargetHost)) {
        return @($result)
    }

    $parsedIp = $null
    if ([System.Net.IPAddress]::TryParse($TargetHost, [ref]$parsedIp) -and $parsedIp.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork) {
        $result.Add($parsedIp.IPAddressToString)
        return @($result | Select-Object -Unique)
    }

    try {
        $addresses = [System.Net.Dns]::GetHostAddresses($TargetHost) |
            Where-Object { $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork } |
            Select-Object -ExpandProperty IPAddressToString -Unique
        foreach ($address in $addresses) {
            $result.Add($address)
        }
    }
    catch {
    }

    return @($result | Select-Object -Unique)
}

function Get-GeoInfoForIp {
    param(
        [string]$IpAddress,
        [string]$SubjectLabel,
        [System.Collections.Generic.List[string]]$Warnings
    )

    $geo = [ordered]@{
        IP        = 'N/A'
        Location  = 'N/A'
        Latitude  = 'N/A'
        Longitude = 'N/A'
        TimeZone  = 'N/A'
        Org       = 'N/A'
    }

    $uri = ''
    if ([string]::IsNullOrWhiteSpace($IpAddress)) {
        $uri = 'https://ipapi.co/json/'
    }
    elseif (Test-IsPrivateIpv4 -IpAddress $IpAddress) {
        $geo.IP = $IpAddress
        $geo.Location = 'Private/Local network'
        $geo.TimeZone = [System.TimeZoneInfo]::Local.Id
        return $geo
    }
    else {
        $uri = "https://ipapi.co/$IpAddress/json/"
    }

    try {
        $response = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec 12
        if ($null -eq $response -or ($response.PSObject.Properties.Name -contains 'error' -and $response.error)) {
            throw 'Geo API returned an error response.'
        }

        $resolvedIp = if (-not [string]::IsNullOrWhiteSpace($response.ip)) { "$($response.ip)" } elseif (-not [string]::IsNullOrWhiteSpace($IpAddress)) { $IpAddress } else { 'N/A' }
        $city = if (-not [string]::IsNullOrWhiteSpace($response.city)) { "$($response.city)" } else { 'N/A' }
        $region = if (-not [string]::IsNullOrWhiteSpace($response.region)) { "$($response.region)" } else { 'N/A' }
        $country = if (-not [string]::IsNullOrWhiteSpace($response.country_name)) { "$($response.country_name)" } else { 'N/A' }

        $geo.IP = $resolvedIp
        $geo.Location = "$city, $region, $country"
        if (-not [string]::IsNullOrWhiteSpace("$($response.latitude)")) { $geo.Latitude = "$($response.latitude)" }
        if (-not [string]::IsNullOrWhiteSpace("$($response.longitude)")) { $geo.Longitude = "$($response.longitude)" }
        if (-not [string]::IsNullOrWhiteSpace("$($response.timezone)")) { $geo.TimeZone = "$($response.timezone)" }
        if (-not [string]::IsNullOrWhiteSpace("$($response.org)")) { $geo.Org = "$($response.org)" }
    }
    catch {
        if (-not [string]::IsNullOrWhiteSpace($IpAddress)) {
            $geo.IP = $IpAddress
        }
    }

    return $geo
}

function Get-LocalHostDemographics {
    param([string]$ScriptFilePath)

    $warnings = New-Object System.Collections.Generic.List[string]
    $hostData = [ordered]@{}
    $platform = Get-OsPlatformInfo

    $hostNameValue = if (-not [string]::IsNullOrWhiteSpace($env:COMPUTERNAME)) {
        $env:COMPUTERNAME
    }
    elseif (-not [string]::IsNullOrWhiteSpace($env:HOSTNAME)) {
        $env:HOSTNAME
    }
    else {
        [System.Net.Dns]::GetHostName()
    }

    $hostUserValue = if (-not [string]::IsNullOrWhiteSpace($env:USERNAME)) {
        $env:USERNAME
    }
    elseif (-not [string]::IsNullOrWhiteSpace($env:USER)) {
        $env:USER
    }
    else {
        [System.Environment]::UserName
    }

    $hostDomainValue = if (-not [string]::IsNullOrWhiteSpace($env:USERDOMAIN)) { $env:USERDOMAIN } else { 'None' }

    $osCaption = "$([System.Runtime.InteropServices.RuntimeInformation]::OSDescription)"
    $osVersion = "$([System.Environment]::OSVersion.VersionString)"
    $osBuild = "$([System.Environment]::OSVersion.Version.Build)"
    $osArchitecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    $processor = [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString()
    $logicalProcessors = [System.Environment]::ProcessorCount
    $physicalMemoryBytes = $null
    $lastBootTimeValue = 'None'

    if ($platform.IsWindows) {
        try {
            $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
            $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
            $cpu = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1

            $osCaption = if ($null -ne $os -and -not [string]::IsNullOrWhiteSpace("$($os.Caption)")) { "$($os.Caption)" } else { $osCaption }
            $osVersion = if ($null -ne $os -and -not [string]::IsNullOrWhiteSpace("$($os.Version)")) { "$($os.Version)" } else { $osVersion }
            $osBuild = if ($null -ne $os -and -not [string]::IsNullOrWhiteSpace("$($os.BuildNumber)")) { "$($os.BuildNumber)" } else { $osBuild }
            $osArchitecture = if ($null -ne $os -and -not [string]::IsNullOrWhiteSpace("$($os.OSArchitecture)")) { "$($os.OSArchitecture)" } else { $osArchitecture }
            $processor = if ($null -ne $cpu -and -not [string]::IsNullOrWhiteSpace("$($cpu.Name)")) { "$($cpu.Name)" } else { $processor }
            $logicalProcessors = if ($null -ne $cs -and $cs.NumberOfLogicalProcessors) { [int]$cs.NumberOfLogicalProcessors } else { $logicalProcessors }
            if ($null -ne $cs -and $cs.TotalPhysicalMemory) {
                $physicalMemoryBytes = [int64]$cs.TotalPhysicalMemory
            }
            if ($null -ne $os -and $os.LastBootUpTime) {
                $lastBootTimeValue = "$($os.LastBootUpTime)"
            }
        }
        catch {
            $warnings.Add("Could not read complete host demographics from Windows CIM. $(($_.Exception.Message).Trim())")
        }
    }
    elseif ($platform.IsLinux) {
        try {
            $memInfoPath = '/proc/meminfo'
            if (Test-Path -LiteralPath $memInfoPath) {
                $memLine = Select-String -Path $memInfoPath -Pattern '^MemTotal:\s+(\d+)\s+kB' -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($null -ne $memLine -and $memLine.Matches.Count -gt 0) {
                    $physicalMemoryBytes = [int64]$memLine.Matches[0].Groups[1].Value * 1KB
                }
            }
        }
        catch {
            $warnings.Add("Could not read Linux memory information from /proc/meminfo. $(($_.Exception.Message).Trim())")
        }
    }
    elseif ($platform.IsMacOS) {
        try {
            $sysctlBytes = & sysctl -n hw.memsize 2>$null
            if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace("$sysctlBytes")) {
                $physicalMemoryBytes = [int64]$sysctlBytes
            }
        }
        catch {
            $warnings.Add("Could not read macOS memory information with sysctl. $(($_.Exception.Message).Trim())")
        }
    }

    $hostIps = @(Resolve-IPv4FromHostName -TargetHost $hostNameValue)
    $geo = Get-GeoInfoForIp -IpAddress '' -SubjectLabel 'execution host' -Warnings $warnings
    $timeZoneId = [System.TimeZoneInfo]::Local.Id
    $timeZoneName = [System.TimeZoneInfo]::Local.DisplayName

    $hostData['Host machine name'] = if (-not [string]::IsNullOrWhiteSpace($hostNameValue)) { $hostNameValue } else { 'None' }
    $hostData['Run directory'] = (Get-Location).Path
    $hostData['Script file'] = $ScriptFilePath
    $hostData['Host user'] = if (-not [string]::IsNullOrWhiteSpace($hostUserValue)) { $hostUserValue } else { 'None' }
    $hostData['Host domain'] = $hostDomainValue
    $hostData['Host OS family'] = $platform.Family
    $hostData['OS caption'] = if (-not [string]::IsNullOrWhiteSpace($osCaption)) { $osCaption } else { 'None' }
    $hostData['OS version'] = if (-not [string]::IsNullOrWhiteSpace($osVersion)) { $osVersion } else { 'None' }
    $hostData['OS build'] = if (-not [string]::IsNullOrWhiteSpace($osBuild)) { $osBuild } else { 'None' }
    $hostData['OS architecture'] = if (-not [string]::IsNullOrWhiteSpace($osArchitecture)) { $osArchitecture } else { 'None' }
    $hostData['Processor'] = if (-not [string]::IsNullOrWhiteSpace($processor)) { $processor } else { 'None' }
    $hostData['Logical processors'] = if ($null -ne $logicalProcessors) { "$logicalProcessors" } else { 'None' }
    $hostData['Physical memory'] = if ($null -ne $physicalMemoryBytes -and $physicalMemoryBytes -gt 0) { (Format-FileSize -Bytes $physicalMemoryBytes) } else { 'None' }
    $hostData['Last boot time'] = if (-not [string]::IsNullOrWhiteSpace($lastBootTimeValue)) { $lastBootTimeValue } else { 'None' }
    $hostData['Local timezone'] = "$timeZoneId ($timeZoneName)"
    $hostData['Local timestamp'] = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $hostData['Host IPv4 addresses'] = if ($hostIps.Count -gt 0) { ($hostIps -join ', ') } else { 'None' }
    $hostData['Public IP'] = if (-not [string]::IsNullOrWhiteSpace($geo.IP) -and $geo.IP -ne 'N/A') { $geo.IP } else { 'None' }
    $hostData['Host location'] = if (-not [string]::IsNullOrWhiteSpace($geo.Location) -and $geo.Location -ne 'N/A') { $geo.Location } else { 'None' }
    $hostData['Host latitude'] = if (-not [string]::IsNullOrWhiteSpace($geo.Latitude) -and $geo.Latitude -ne 'N/A') { $geo.Latitude } else { 'None' }
    $hostData['Host longitude'] = if (-not [string]::IsNullOrWhiteSpace($geo.Longitude) -and $geo.Longitude -ne 'N/A') { $geo.Longitude } else { 'None' }
    $hostData['Geo timezone'] = if (-not [string]::IsNullOrWhiteSpace($geo.TimeZone) -and $geo.TimeZone -ne 'N/A') { $geo.TimeZone } else { 'None' }
    $hostData['Network org'] = if (-not [string]::IsNullOrWhiteSpace($geo.Org) -and $geo.Org -ne 'N/A') { $geo.Org } else { 'None' }

    $restrictedFields = New-Object System.Collections.Generic.List[string]
    foreach ($key in @('OS caption', 'OS version', 'OS build', 'OS architecture', 'Processor', 'Logical processors', 'Physical memory', 'Last boot time', 'Public IP', 'Host location', 'Host latitude', 'Host longitude', 'Geo timezone', 'Network org')) {
        if ($hostData[$key] -eq 'None') {
            $restrictedFields.Add($key)
        }
    }
    if ($restrictedFields.Count -gt 0) {
        $warnings.Add("Some host demographics are unavailable/restricted on this machine: $($restrictedFields -join ', ')")
    }

    return [pscustomobject]@{
        Data     = $hostData
        GeoData  = $geo
        Warnings = $warnings
    }
}

function Get-PostgresServerDemographics {
    param(
        [string]$DbHost,
        [int]$DbPort,
        [System.Collections.IDictionary]$SummaryMetrics
    )

    $warnings = New-Object System.Collections.Generic.List[string]
    $serverData = [ordered]@{}

    $resolvedIps = @(Resolve-IPv4FromHostName -TargetHost $DbHost)
    $serverAddr = Get-MetricValueOrDefault -Metrics $SummaryMetrics -Key 'server_addr'

    $serverData['Configured DB host'] = $DbHost
    $serverData['Configured DB port'] = "$DbPort"
    $serverData['Resolved DB host IPv4'] = if ($resolvedIps.Count -gt 0) { ($resolvedIps -join ', ') } else { 'N/A' }
    $serverData['Server-reported address'] = $serverAddr
    $serverData['Server-reported port'] = Get-MetricValueOrDefault -Metrics $SummaryMetrics -Key 'server_port'
    $serverData['Client address seen by DB'] = Get-MetricValueOrDefault -Metrics $SummaryMetrics -Key 'client_addr'
    $serverData['PostgreSQL version'] = Get-MetricValueOrDefault -Metrics $SummaryMetrics -Key 'server_version'
    $serverData['PostgreSQL timezone'] = Get-MetricValueOrDefault -Metrics $SummaryMetrics -Key 'server_timezone'
    $serverData['PostgreSQL data directory'] = Get-MetricValueOrDefault -Metrics $SummaryMetrics -Key 'server_data_directory'
    $serverData['PostgreSQL current user'] = Get-MetricValueOrDefault -Metrics $SummaryMetrics -Key 'current_db_user'
    $serverData['Postmaster start time'] = Get-MetricValueOrDefault -Metrics $SummaryMetrics -Key 'postmaster_start_time'
    $serverData['Server recovery mode'] = Get-MetricValueOrDefault -Metrics $SummaryMetrics -Key 'server_is_in_recovery'

    return [pscustomobject]@{
        Data     = $serverData
        Warnings = $warnings
    }
}

function Escape-MarkdownCell {
    param([string]$Value)

    if ($null -eq $Value) {
        return ''
    }

    $escaped = "$Value" -replace '\|', '\|'
    $escaped = $escaped -replace "(`r`n|`n|`r)", '<br/>'
    return $escaped
}

function Add-ReportRow {
    param(
        [System.Collections.Generic.List[object]]$Rows,
        [string]$Category,
        [string]$Field,
        [string]$Value
    )

    $Rows.Add([pscustomobject]@{
            Category = $Category
            Field    = $Field
            Value    = $Value
        }) | Out-Null
}

function Build-MarkdownReport {
    param(
        [System.Collections.Generic.List[object]]$Rows,
        [System.Collections.Generic.List[string]]$Warnings
    )

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add('# Database Backup Summary') | Out-Null
    $lines.Add('') | Out-Null
    $lines.Add('| Category | Field | Value |') | Out-Null
    $lines.Add('|---|---|---|') | Out-Null

    foreach ($row in $Rows) {
        $lines.Add("| $(Escape-MarkdownCell -Value $row.Category) | $(Escape-MarkdownCell -Value $row.Field) | $(Escape-MarkdownCell -Value $row.Value) |") | Out-Null
    }

    if ($Warnings.Count -gt 0) {
        $lines.Add('') | Out-Null
        $lines.Add('## Attention Items') | Out-Null
        foreach ($warning in $Warnings) {
            $lines.Add("- $(Escape-MarkdownCell -Value $warning)") | Out-Null
        }
    }

    return ($lines -join [Environment]::NewLine)
}

function Invoke-DatabaseDump {
    param(
        [string]$PgDumpExecutable,
        [string]$OutputFile,
        [string]$Database,
        [string]$User,
        [string]$DbHost,
        [int]$DbPort,
        [switch]$SchemaOnly
    )

    $pgDumpArgs = @(
        '-h', $DbHost
        '-p', "$DbPort"
        '-U', $User
        '-d', $Database
        '--format=plain'
        '--no-owner'
        '--no-privileges'
        '--encoding=UTF8'
        '-f', $OutputFile
    )
    if ($SchemaOnly) {
        $pgDumpArgs += '--schema-only'
    }

    & $PgDumpExecutable @pgDumpArgs
    if ($LASTEXITCODE -ne 0) {
        $label = if ($SchemaOnly) { 'Schema-only backup' } else { 'Full backup' }
        Write-Host "$label FAILED! Error code: $LASTEXITCODE" -ForegroundColor Red
        exit 1
    }
}

function Write-BackupSummary {
    param(
        [System.IO.FileInfo]$BackupInfo,
        [string]$Project,
        [string]$Database,
        [string]$User,
        [string]$DbHost,
        [int]$DbPort,
        [object]$SummaryData,
        [object]$LocalHostData,
        [System.IO.FileInfo]$SchemaBackupInfo = $null
    )

    $successIcon = [char]0x2705
    $allWarnings = New-Object System.Collections.Generic.List[string]

    foreach ($warning in $SummaryData.Warnings) {
        $allWarnings.Add($warning)
    }
    foreach ($warning in $LocalHostData.Warnings) {
        $allWarnings.Add($warning)
    }
    $dbBackupStatusIcon = $successIcon
    $dbBackupStatusText = 'Full backup file (schema + data) created successfully'
    $schemaBackupStatusIcon = $successIcon
    $schemaBackupStatusText = if ($null -ne $SchemaBackupInfo) {
        'Schema-only backup file created successfully'
    }
    else {
        'Schema-only backup skipped'
    }
    $hostStatusIcon = $successIcon
    $hostStatusText = if ($LocalHostData.Warnings.Count -gt 0) { 'Host demographics captured (partial values set to None)' } else { 'Host demographics captured successfully' }
    $statusText = 'Backup completed successfully.'
    $statusColor = 'Green'
    $statusIcon = $successIcon

    $estimatedRecords = Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'estimated_record_count'
    if ($estimatedRecords -ne 'N/A') {
        try {
            $estimatedRecords = ('{0:N0}' -f [double]$estimatedRecords) + ' (estimated)'
        }
        catch {
        }
    }

    $rows = New-Object System.Collections.Generic.List[object]
    Add-ReportRow -Rows $rows -Category 'Status' -Field 'Full DB backup status' -Value "$dbBackupStatusIcon $dbBackupStatusText"
    Add-ReportRow -Rows $rows -Category 'Status' -Field 'Schema-only backup status' -Value "$schemaBackupStatusIcon $schemaBackupStatusText"
    Add-ReportRow -Rows $rows -Category 'Status' -Field 'Execution host demographics status' -Value "$hostStatusIcon $hostStatusText"
    Add-ReportRow -Rows $rows -Category 'Status' -Field 'Overall summary status' -Value "$statusIcon $statusText"
    Add-ReportRow -Rows $rows -Category 'Status' -Field 'Warnings count' -Value "$($allWarnings.Count)"

    Add-ReportRow -Rows $rows -Category 'Backup' -Field 'Project' -Value $Project
    Add-ReportRow -Rows $rows -Category 'Backup' -Field 'Database' -Value $Database
    Add-ReportRow -Rows $rows -Category 'Backup' -Field 'Connection' -Value "$User@$DbHost`:$DbPort"
    Add-ReportRow -Rows $rows -Category 'Backup (full)' -Field 'Backup file name' -Value $BackupInfo.Name
    Add-ReportRow -Rows $rows -Category 'Backup (full)' -Field 'Backup file path' -Value $BackupInfo.FullName
    Add-ReportRow -Rows $rows -Category 'Backup (full)' -Field 'Backup timestamp' -Value $BackupInfo.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
    Add-ReportRow -Rows $rows -Category 'Backup (full)' -Field 'Dump size' -Value (Format-FileSize -Bytes $BackupInfo.Length)
    if ($null -ne $SchemaBackupInfo) {
        Add-ReportRow -Rows $rows -Category 'Backup (schema only)' -Field 'Schema file name' -Value $SchemaBackupInfo.Name
        Add-ReportRow -Rows $rows -Category 'Backup (schema only)' -Field 'Schema file path' -Value $SchemaBackupInfo.FullName
        Add-ReportRow -Rows $rows -Category 'Backup (schema only)' -Field 'Schema dump size' -Value (Format-FileSize -Bytes $SchemaBackupInfo.Length)
        Add-ReportRow -Rows $rows -Category 'Backup (schema only)' -Field 'Contents' -Value 'DDL only (tables, indexes, constraints, views, functions, triggers — no COPY/data)'
    }
    else {
        Add-ReportRow -Rows $rows -Category 'Backup (schema only)' -Field 'Schema file' -Value 'Not created (-SkipSchemaDump)'
    }
    Add-ReportRow -Rows $rows -Category 'Backup' -Field 'Database size' -Value (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'database_size')
    Add-ReportRow -Rows $rows -Category 'Backup' -Field 'Record count' -Value $estimatedRecords

    Add-ReportRow -Rows $rows -Category 'Database Objects' -Field 'Tables' -Value (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'table_count')
    Add-ReportRow -Rows $rows -Category 'Database Objects' -Field 'Constraints' -Value (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'constraint_count')
    Add-ReportRow -Rows $rows -Category 'Database Objects' -Field 'Indexes' -Value (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'index_count')
    Add-ReportRow -Rows $rows -Category 'Database Objects' -Field 'Views' -Value (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'view_count')
    Add-ReportRow -Rows $rows -Category 'Database Objects' -Field 'Functions' -Value (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'function_count')
    Add-ReportRow -Rows $rows -Category 'Database Objects' -Field 'Triggers' -Value (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'trigger_count')

    foreach ($key in $LocalHostData.Data.Keys) {
        Add-ReportRow -Rows $rows -Category 'Execution Host' -Field "$key" -Value "$($LocalHostData.Data[$key])"
    }

    $reportMarkdown = Build-MarkdownReport -Rows $rows -Warnings $allWarnings
    $reportPath = [System.IO.Path]::ChangeExtension($BackupInfo.FullName, '.summary.md')
    Set-Content -LiteralPath $reportPath -Value $reportMarkdown -Encoding UTF8

    Write-Host ''
    Write-Host "$statusIcon $statusText" -ForegroundColor $statusColor
    Write-Host "$dbBackupStatusIcon Full DB backup status: $dbBackupStatusText" -ForegroundColor Green
    Write-Host "$schemaBackupStatusIcon Schema-only backup status: $schemaBackupStatusText" -ForegroundColor Green
    Write-Host "$hostStatusIcon Host demographics status: $hostStatusText" -ForegroundColor Green
    Write-Host "Markdown report saved: $reportPath" -ForegroundColor Cyan
    Write-Host ''
    Write-Host 'Backup summary:'
    Write-Host ("  {0,-22} : {1}" -f 'Project', $Project)
    Write-Host ("  {0,-22} : {1}" -f 'Connection', "$User@$DbHost`:$DbPort")
    Write-Host ("  {0,-22} : {1}" -f 'Database', $Database)
    Write-Host ("  {0,-22} : {1}" -f 'Backup timestamp', $BackupInfo.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))
    Write-Host ("  {0,-22} : {1}" -f 'Dump size', (Format-FileSize -Bytes $BackupInfo.Length))
    Write-Host ("  {0,-22} : {1}" -f 'Tables', (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'table_count'))
    Write-Host ("  {0,-22} : {1}" -f 'Constraints', (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'constraint_count'))
    Write-Host ("  {0,-22} : {1}" -f 'Indexes', (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'index_count'))
    Write-Host ("  {0,-22} : {1}" -f 'Views', (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'view_count'))
    Write-Host ("  {0,-22} : {1}" -f 'Functions', (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'function_count'))
    Write-Host ("  {0,-22} : {1}" -f 'Triggers', (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'trigger_count'))
    Write-Host ("  {0,-22} : {1}" -f 'Record count', $estimatedRecords)
    Write-Host ("  {0,-22} : {1}" -f 'Database size', (Get-MetricValueOrDefault -Metrics $SummaryData.Metrics -Key 'database_size'))
    Write-Host ("  {0,-22} : {1}" -f 'Full backup file', $BackupInfo.FullName)
    if ($null -ne $SchemaBackupInfo) {
        Write-Host ("  {0,-22} : {1}" -f 'Schema-only file', $SchemaBackupInfo.FullName)
        Write-Host ("  {0,-22} : {1}" -f 'Schema dump size', (Format-FileSize -Bytes $SchemaBackupInfo.Length))
    }
    Write-Host ("  {0,-22} : {1}" -f 'Host machine name', $LocalHostData.Data['Host machine name'])
    Write-Host ("  {0,-22} : {1}" -f 'Host user', $LocalHostData.Data['Host user'])
    Write-Host ("  {0,-22} : {1}" -f 'Host domain', $LocalHostData.Data['Host domain'])
    Write-Host ("  {0,-22} : {1}" -f 'Run directory', $LocalHostData.Data['Run directory'])
    Write-Host ("  {0,-22} : {1}" -f 'Script file', $LocalHostData.Data['Script file'])
    Write-Host ("  {0,-22} : {1}" -f 'Host OS family', $LocalHostData.Data['Host OS family'])
    Write-Host ("  {0,-22} : {1}" -f 'OS caption', $LocalHostData.Data['OS caption'])
    Write-Host ("  {0,-22} : {1}" -f 'OS version', $LocalHostData.Data['OS version'])
    Write-Host ("  {0,-22} : {1}" -f 'OS build', $LocalHostData.Data['OS build'])
    Write-Host ("  {0,-22} : {1}" -f 'OS architecture', $LocalHostData.Data['OS architecture'])
    Write-Host ("  {0,-22} : {1}" -f 'Processor', $LocalHostData.Data['Processor'])
    Write-Host ("  {0,-22} : {1}" -f 'Logical processors', $LocalHostData.Data['Logical processors'])
    Write-Host ("  {0,-22} : {1}" -f 'Physical memory', $LocalHostData.Data['Physical memory'])
    Write-Host ("  {0,-22} : {1}" -f 'Last boot time', $LocalHostData.Data['Last boot time'])
    Write-Host ("  {0,-22} : {1}" -f 'Local timezone', $LocalHostData.Data['Local timezone'])
    Write-Host ("  {0,-22} : {1}" -f 'Host IPv4 addresses', $LocalHostData.Data['Host IPv4 addresses'])
    Write-Host ("  {0,-22} : {1}" -f 'Public IP', $LocalHostData.Data['Public IP'])
    Write-Host ("  {0,-22} : {1}" -f 'Host location', $LocalHostData.Data['Host location'])
    Write-Host ("  {0,-22} : {1}" -f 'Host latitude', $LocalHostData.Data['Host latitude'])
    Write-Host ("  {0,-22} : {1}" -f 'Host longitude', $LocalHostData.Data['Host longitude'])
    Write-Host ("  {0,-22} : {1}" -f 'Geo timezone', $LocalHostData.Data['Geo timezone'])
    Write-Host ("  {0,-22} : {1}" -f 'Network org', $LocalHostData.Data['Network org'])

    if ($allWarnings.Count -gt 0) {
        Write-Host ''
        foreach ($warning in $allWarnings) {
            Write-Host "NOTE: $warning" -ForegroundColor Yellow
        }
    }
}

$resolvedBackupDir = Resolve-BackupDirectory -Path $BackupDirectory
if (-not (Test-Path -LiteralPath $resolvedBackupDir)) {
    $null = New-Item -ItemType Directory -Path $resolvedBackupDir -Force
}

$timestamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$backupFileName = "$($ProjectName)_db_backup_full_$timestamp.sql"
$backupFile = Join-Path -Path $resolvedBackupDir -ChildPath $backupFileName
$schemaFileName = "$($ProjectName)_db_schema_$timestamp.sql"
$schemaFile = Join-Path -Path $resolvedBackupDir -ChildPath $schemaFileName

if (-not $SkipPasswordPrompt) {
    $securePwd = Read-Host -AsSecureString "PostgreSQL password for user '$UserName' (leave empty if not required)"
    if ($null -ne $securePwd -and $securePwd.Length -gt 0) {
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePwd)
        try {
            $env:PGPASSWORD = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        }
        finally {
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
}

try {
    Write-Host "Creating full backup (schema + data): $backupFileName" -ForegroundColor Cyan
    Invoke-DatabaseDump -PgDumpExecutable $PgDumpPath -OutputFile $backupFile -Database $DatabaseName `
        -User $UserName -DbHost $HostName -DbPort $Port

    $schemaBackupInfo = $null
    if (-not $SkipSchemaDump) {
        Write-Host "Creating schema-only backup (no data): $schemaFileName" -ForegroundColor Cyan
        Invoke-DatabaseDump -PgDumpExecutable $PgDumpPath -OutputFile $schemaFile -Database $DatabaseName `
            -User $UserName -DbHost $HostName -DbPort $Port -SchemaOnly
        $schemaBackupInfo = Get-Item -LiteralPath $schemaFile -ErrorAction Stop
    }

    $backupInfo = Get-Item -LiteralPath $backupFile -ErrorAction Stop
    $summaryData = Get-BackupSummaryData -RequestedPsqlPath $PsqlPath -PgDumpExecutable $PgDumpPath -Database $DatabaseName -User $UserName -DbHost $HostName -DbPort $Port
    $localHostData = Get-LocalHostDemographics -ScriptFilePath $PSCommandPath
    Write-BackupSummary -BackupInfo $backupInfo -Project $ProjectName -Database $DatabaseName -User $UserName `
        -DbHost $HostName -DbPort $Port -SummaryData $summaryData -LocalHostData $localHostData `
        -SchemaBackupInfo $schemaBackupInfo

    if ($RetentionDays -gt 0) {
        $cutoff = (Get-Date).AddDays(-$RetentionDays)
        $retentionPatterns = @(
            "$ProjectName" + '_db_backup_full_*.sql',
            "$ProjectName" + '_db_schema_*.sql',
            "$ProjectName" + '_db_backup_full_*.summary.md'
        )
        foreach ($pattern in $retentionPatterns) {
            Get-ChildItem -LiteralPath $resolvedBackupDir -File -Filter $pattern -ErrorAction SilentlyContinue |
                Where-Object { $_.LastWriteTime -lt $cutoff } |
                ForEach-Object {
                    Remove-Item -LiteralPath $_.FullName -Force
                    Write-Host "Removed old backup (retention ${RetentionDays}d): $($_.Name)" -ForegroundColor DarkYellow
                }
        }
    }
}
finally {
    Remove-PgPasswordEnv
}
