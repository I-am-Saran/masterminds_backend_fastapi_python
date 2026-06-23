#Requires -Version 5.1
# ======================================================
# Full Manual Database Restore Script (PowerShell)
# ======================================================
# Restores a plain-text SQL dump produced by full_manual_db_backup_script.ps1
# (pg_dump --format=plain). Do NOT use pg_restore for those .sql files.
#
# Examples:
#   pwsh ./full_manual_db_restore_script.ps1 -BackupFile .\kaizen_db_backup_full_2026-05-23_09-32-29.sql
#   pwsh ./full_manual_db_restore_script.ps1 -UseLatestBackup
#   pwsh ./full_manual_db_restore_script.ps1 -BackupFile .\backup.sql -RecreateDatabase -Force
#
# Linux (peer auth / permission denied with -f): auto-uses shell stdin redirect via sudo -u postgres
# when -UseLinuxSudoPostgres is set (default on Linux when connecting as postgres to localhost).

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    # Path to a plain .sql dump. Required unless -UseLatestBackup is set.
    [Parameter()][string]$BackupFile,

    # Pick the newest {ProjectName}_db_backup_full_*.sql under BackupDirectory.
    [Parameter()][switch]$UseLatestBackup,

    [Parameter()][string]$ProjectName = 'kaizen',
    [Parameter()][string]$DatabaseName = 'kaizen_dev',
    [Parameter()][string]$AdminDatabase = 'postgres',
    [Parameter()][string]$UserName = 'postgres',
    [Parameter()][string]$HostName = 'localhost',
    [Parameter()][ValidateRange(1, 65535)][int]$Port = 5432,

    [Parameter()][string]$BackupDirectory = '.',
    [Parameter()][string]$PsqlPath = 'psql',

    # Create target database when it does not exist (connects using AdminDatabase).
    [Parameter()][switch]$CreateDatabaseIfMissing,

    # Drop and recreate target database before restore (destructive). Use -Force to skip confirmation.
    [Parameter()][switch]$RecreateDatabase,

    # Linux: run psql as OS user postgres via sudo with stdin redirect (avoids -f permission issues).
    [Parameter()][switch]$UseLinuxSudoPostgres,

    # Skip interactive confirmation when -RecreateDatabase is set (CI / trusted environments only).
    [Parameter()][switch]$Force,

    [Parameter()][switch]$SkipPasswordPrompt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-DirectoryPath {
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
    if ($platformWindows) { $family = 'Windows' }
    elseif ($platformLinux) { $family = 'Linux' }
    elseif ($platformMacOS) { $family = 'macOS' }

    return [pscustomobject]@{
        IsWindows = $platformWindows
        IsLinux   = $platformLinux
        IsMacOS   = $platformMacOS
        Family    = $family
    }
}

function Format-FileSize {
    param([long]$Bytes)
    if ($Bytes -lt 1KB) { return "$Bytes B" }
    if ($Bytes -lt 1MB) { return ('{0:N2} KB' -f ($Bytes / 1KB)) }
    if ($Bytes -lt 1GB) { return ('{0:N2} MB' -f ($Bytes / 1GB)) }
    return ('{0:N2} GB' -f ($Bytes / 1GB))
}

function Escape-BashSingleQuoted {
    param([string]$Value)
    return ($Value -replace "'", "'\''")
}

function Escape-MarkdownCell {
    param([string]$Value)
    if ($null -eq $Value) { return '' }
    $escaped = "$Value" -replace '\|', '\|'
    return ($escaped -replace "(`r`n|`n|`r)", '<br/>')
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
        [string]$Title,
        [System.Collections.Generic.List[object]]$Rows,
        [System.Collections.Generic.List[string]]$Warnings
    )
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("# $Title") | Out-Null
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

function Invoke-Psql {
    param(
        [string]$ExecutablePath,
        [string]$Database,
        [string]$User,
        [string]$DbHost,
        [int]$DbPort,
        [string[]]$ExtraArgs = @(),
        [string]$SqlCommand,
        [switch]$UseLinuxSudoPostgres
    )

    $baseArgs = @(
        '-h', $DbHost
        '-p', "$DbPort"
        '-U', $User
        '-d', $Database
        '-v', 'ON_ERROR_STOP=1'
    ) + $ExtraArgs

    if ($SqlCommand) {
        $baseArgs += @('-c', $SqlCommand)
    }

    if ($UseLinuxSudoPostgres) {
        $argString = ($baseArgs | ForEach-Object {
                if ($_ -match '\s') { "'$($_ -replace "'", "'\''")'" } else { $_ }
            }) -join ' '
        $bashCommand = "sudo -u postgres $ExecutablePath $argString"
        $output = & bash -c $bashCommand 2>&1
        return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($output) }
    }

    $output = & $ExecutablePath @baseArgs 2>&1
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($output) }
}

function Invoke-PsqlMetricsQuery {
    param(
        [string]$ExecutablePath,
        [string]$Database,
        [string]$User,
        [string]$DbHost,
        [int]$DbPort,
        [switch]$UseLinuxSudoPostgres
    )

    $sql = @"
SELECT 'table_count', COUNT(*)::text
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
  AND table_type = 'BASE TABLE'
UNION ALL
SELECT 'estimated_record_count', COALESCE(SUM(n_live_tup), 0)::bigint::text
FROM pg_stat_user_tables
UNION ALL
SELECT 'database_size', pg_size_pretty(pg_database_size(current_database()))
UNION ALL
SELECT 'server_version', current_setting('server_version');
"@

    if ($UseLinuxSudoPostgres) {
        $escapedSql = $sql -replace "'", "'\''"
        $bashCommand = @"
sudo -u postgres $ExecutablePath -h '$DbHost' -p '$DbPort' -U '$User' -d '$Database' -X -A -t -F '|' -v ON_ERROR_STOP=1 -c '$escapedSql'
"@
        $output = & bash -c $bashCommand 2>&1
        return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($output) }
    }

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
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($output) }
}

function Test-PlainSqlDumpFile {
    param([string]$Path)

    $info = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($info.Length -lt 32) {
        throw "Backup file is too small to be a valid PostgreSQL dump: $Path"
    }

    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $buffer = New-Object byte[] 64
        $read = $stream.Read($buffer, 0, $buffer.Length)
        $header = [System.Text.Encoding]::ASCII.GetString($buffer, 0, $read)
    }
    finally {
        $stream.Dispose()
    }

    if ($header.StartsWith('PGDMP')) {
        throw @"
Backup file is a pg_dump custom/archive format (PGDMP header), not plain SQL.
Use pg_restore instead of this script, or re-export with full_manual_db_backup_script.ps1 (--format=plain).
File: $Path
"@
    }

    if ($header -notmatch 'PostgreSQL database dump') {
        throw "File does not look like a plain pg_dump SQL file (missing 'PostgreSQL database dump' header): $Path"
    }

    return $info
}

function Get-LatestBackupFile {
    param(
        [string]$Directory,
        [string]$Project
    )

    $pattern = "$Project" + '_db_backup_full_*.sql'
    $latest = Get-ChildItem -LiteralPath $Directory -File -Filter $pattern -ErrorAction Stop |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($null -eq $latest) {
        throw "No backup files matching '$pattern' found in: $Directory"
    }

    return $latest
}

function Test-DatabaseExists {
    param(
        [string]$ExecutablePath,
        [string]$Database,
        [string]$User,
        [string]$DbHost,
        [int]$DbPort,
        [string]$AdminDatabase,
        [switch]$UseLinuxSudoPostgres
    )

    $sql = "SELECT 1 FROM pg_database WHERE datname = '$($Database -replace "'", "''")';"
    $result = Invoke-Psql -ExecutablePath $ExecutablePath -Database $AdminDatabase -User $User -DbHost $DbHost -DbPort $DbPort `
        -SqlCommand $sql -UseLinuxSudoPostgres:$UseLinuxSudoPostgres
    if ($result.ExitCode -ne 0) {
        throw "Failed to query database catalog. $($result.Output -join ' ')"
    }
    return ($result.Output -match '^\s*1\s*$')
}

function Invoke-RecreateDatabase {
    param(
        [string]$ExecutablePath,
        [string]$Database,
        [string]$User,
        [string]$DbHost,
        [int]$DbPort,
        [string]$AdminDatabase,
        [switch]$UseLinuxSudoPostgres
    )

    Write-Host "Recreating database '$Database'..." -ForegroundColor Yellow

    $terminateSql = @"
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$($Database -replace "'", "''")' AND pid <> pg_backend_pid();
"@
    $null = Invoke-Psql -ExecutablePath $ExecutablePath -Database $AdminDatabase -User $User -DbHost $DbHost -DbPort $DbPort `
        -SqlCommand $terminateSql -UseLinuxSudoPostgres:$UseLinuxSudoPostgres

    $dropSql = "DROP DATABASE IF EXISTS `"$($Database -replace '"', '""')`";"
    $createSql = "CREATE DATABASE `"$($Database -replace '"', '""')`";"

    foreach ($command in @($dropSql, $createSql)) {
        $result = Invoke-Psql -ExecutablePath $ExecutablePath -Database $AdminDatabase -User $User -DbHost $DbHost -DbPort $DbPort `
            -SqlCommand $command -UseLinuxSudoPostgres:$UseLinuxSudoPostgres
        if ($result.ExitCode -ne 0) {
            throw "Database recreate failed on: $command`n$($result.Output -join "`n")"
        }
    }
}

function Invoke-CreateDatabaseIfMissing {
    param(
        [string]$ExecutablePath,
        [string]$Database,
        [string]$User,
        [string]$DbHost,
        [int]$DbPort,
        [string]$AdminDatabase,
        [switch]$UseLinuxSudoPostgres
    )

    if (Test-DatabaseExists -ExecutablePath $ExecutablePath -Database $Database -User $User -DbHost $DbHost -DbPort $DbPort `
            -AdminDatabase $AdminDatabase -UseLinuxSudoPostgres:$UseLinuxSudoPostgres) {
        Write-Host "Database '$Database' already exists." -ForegroundColor DarkGray
        return
    }

    Write-Host "Creating database '$Database'..." -ForegroundColor Cyan
    $createSql = "CREATE DATABASE `"$($Database -replace '"', '""')`";"
    $result = Invoke-Psql -ExecutablePath $ExecutablePath -Database $AdminDatabase -User $User -DbHost $DbHost -DbPort $DbPort `
        -SqlCommand $createSql -UseLinuxSudoPostgres:$UseLinuxSudoPostgres
    if ($result.ExitCode -ne 0) {
        throw "CREATE DATABASE failed.`n$($result.Output -join "`n")"
    }
}

function Invoke-PlainSqlRestore {
    param(
        [string]$ExecutablePath,
        [string]$BackupFilePath,
        [string]$Database,
        [string]$User,
        [string]$DbHost,
        [int]$DbPort,
        [switch]$UseLinuxSudoPostgres
    )

    Write-Host "Restoring plain SQL dump into '$Database'..." -ForegroundColor Cyan
    Write-Host "  File: $BackupFilePath" -ForegroundColor DarkGray
    Write-Host "  Size: $(Format-FileSize -Bytes (Get-Item -LiteralPath $BackupFilePath).Length)" -ForegroundColor DarkGray

    $psqlArgs = "-h '$DbHost' -p '$DbPort' -U '$User' -d '$Database' -v ON_ERROR_STOP=1 -q"

    if ($UseLinuxSudoPostgres) {
        # Shell opens the file as the current user; psql runs as postgres (fixes home-dir permission denied).
        $escapedFile = Escape-BashSingleQuoted -Value $BackupFilePath
        $bashCommand = "sudo -u postgres $ExecutablePath $psqlArgs < '$escapedFile'"
        Write-Host "  Method: Linux sudo + stdin redirect" -ForegroundColor DarkGray
        $output = & bash -c $bashCommand 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Restore failed (exit $LASTEXITCODE).`n$($output | Select-Object -Last 40 -join "`n")"
        }
        return @($output)
    }

    # Direct: stream file into psql stdin (works when PGPASSWORD/auth is configured).
    Write-Host "  Method: psql stdin (direct)" -ForegroundColor DarkGray
    $argList = @(
        '-h', $DbHost
        '-p', "$DbPort"
        '-U', $User
        '-d', $Database
        '-v', 'ON_ERROR_STOP=1'
        '-q'
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $ExecutablePath
    $psi.Arguments = ($argList | ForEach-Object {
            if ($_ -match '\s') { """$_""" } else { $_ }
        }) -join ' '
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    $process = [System.Diagnostics.Process]::Start($psi)
    if ($null -eq $process) {
        throw 'Failed to start psql process.'
    }

    try {
        $inputStream = $process.StandardInput.BaseStream
        $fileStream = [System.IO.File]::OpenRead($BackupFilePath)
        try {
            $fileStream.CopyTo($inputStream)
        }
        finally {
            $fileStream.Dispose()
        }
        $process.StandardInput.Close()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
    }
    finally {
        if (-not $process.HasExited) {
            $process.Kill()
        }
        $process.Dispose()
    }

    $combined = @()
    if (-not [string]::IsNullOrWhiteSpace($stdout)) { $combined += $stdout -split "`n" }
    if (-not [string]::IsNullOrWhiteSpace($stderr)) { $combined += $stderr -split "`n" }

    if ($process.ExitCode -ne 0) {
        throw "Restore failed (exit $($process.ExitCode)).`n$($combined | Select-Object -Last 40 -join "`n")"
    }

    return $combined
}

function Confirm-DestructiveRestore {
    param(
        [string]$Database,
        [switch]$Force
    )

    if ($Force) {
        return
    }

    Write-Host ''
    Write-Host "WARNING: -RecreateDatabase will DROP and recreate '$Database'." -ForegroundColor Red
    $typed = Read-Host "Type the database name '$Database' to continue"
    if ($typed -ne $Database) {
        throw 'Confirmation failed. Restore cancelled.'
    }
}

function Write-RestoreSummary {
    param(
        [System.IO.FileInfo]$BackupInfo,
        [string]$Project,
        [string]$Database,
        [string]$User,
        [string]$DbHost,
        [int]$DbPort,
        [string]$RestoreMethod,
        [TimeSpan]$Duration,
        [System.Collections.IDictionary]$Metrics,
        [System.Collections.Generic.List[string]]$Warnings
    )

    $successIcon = [char]0x2705
    $rows = New-Object System.Collections.Generic.List[object]
    Add-ReportRow -Rows $rows -Category 'Status' -Field 'Restore status' -Value "$successIcon Restore completed successfully"
    Add-ReportRow -Rows $rows -Category 'Status' -Field 'Warnings count' -Value "$($Warnings.Count)"
    Add-ReportRow -Rows $rows -Category 'Restore' -Field 'Project' -Value $Project
    Add-ReportRow -Rows $rows -Category 'Restore' -Field 'Target database' -Value $Database
    Add-ReportRow -Rows $rows -Category 'Restore' -Field 'Connection' -Value "$User@$DbHost`:$DbPort"
    Add-ReportRow -Rows $rows -Category 'Restore' -Field 'Restore method' -Value $RestoreMethod
    Add-ReportRow -Rows $rows -Category 'Restore' -Field 'Duration' -Value ('{0:mm\:ss}' -f $Duration)
    Add-ReportRow -Rows $rows -Category 'Restore' -Field 'Backup file' -Value $BackupInfo.FullName
    Add-ReportRow -Rows $rows -Category 'Restore' -Field 'Backup file size' -Value (Format-FileSize -Bytes $BackupInfo.Length)
    Add-ReportRow -Rows $rows -Category 'Restore' -Field 'Backup timestamp' -Value $BackupInfo.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
    Add-ReportRow -Rows $rows -Category 'Post-restore' -Field 'Tables' -Value (Get-MetricValueOrDefault -Metrics $Metrics -Key 'table_count')
    Add-ReportRow -Rows $rows -Category 'Post-restore' -Field 'Record count (est.)' -Value (Get-MetricValueOrDefault -Metrics $Metrics -Key 'estimated_record_count')
    Add-ReportRow -Rows $rows -Category 'Post-restore' -Field 'Database size' -Value (Get-MetricValueOrDefault -Metrics $Metrics -Key 'database_size')
    Add-ReportRow -Rows $rows -Category 'Post-restore' -Field 'Server version' -Value (Get-MetricValueOrDefault -Metrics $Metrics -Key 'server_version')

    $timestamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
    $reportPath = Join-Path -Path $BackupInfo.DirectoryName -ChildPath "$Project`_db_restore_$timestamp.summary.md"
    $reportMarkdown = Build-MarkdownReport -Title 'Database Restore Summary' -Rows $rows -Warnings $Warnings
    Set-Content -LiteralPath $reportPath -Value $reportMarkdown -Encoding UTF8

    Write-Host ''
    Write-Host "$successIcon Restore completed successfully." -ForegroundColor Green
    Write-Host "Markdown report saved: $reportPath" -ForegroundColor Cyan
    Write-Host ''
    Write-Host 'Restore summary:'
    Write-Host ("  {0,-22} : {1}" -f 'Target database', $Database)
    Write-Host ("  {0,-22} : {1}" -f 'Connection', "$User@$DbHost`:$DbPort")
    Write-Host ("  {0,-22} : {1}" -f 'Restore method', $RestoreMethod)
    Write-Host ("  {0,-22} : {1}" -f 'Duration', ('{0:mm\:ss}' -f $Duration))
    Write-Host ("  {0,-22} : {1}" -f 'Tables', (Get-MetricValueOrDefault -Metrics $Metrics -Key 'table_count'))
    Write-Host ("  {0,-22} : {1}" -f 'Database size', (Get-MetricValueOrDefault -Metrics $Metrics -Key 'database_size'))
    Write-Host ("  {0,-22} : {1}" -f 'Backup file', $BackupInfo.FullName)

    if ($Warnings.Count -gt 0) {
        Write-Host ''
        foreach ($warning in $Warnings) {
            Write-Host "NOTE: $warning" -ForegroundColor Yellow
        }
    }
}

# --- Main ---

$platform = Get-OsPlatformInfo
$resolvedBackupDir = Resolve-DirectoryPath -Path $BackupDirectory
$warnings = New-Object System.Collections.Generic.List[string]

if ($UseLatestBackup) {
    $backupItem = Get-LatestBackupFile -Directory $resolvedBackupDir -Project $ProjectName
    $BackupFile = $backupItem.FullName
    Write-Host "Using latest backup: $($backupItem.Name)" -ForegroundColor Cyan
}
elseif ([string]::IsNullOrWhiteSpace($BackupFile)) {
    throw 'Specify -BackupFile <path.sql> or -UseLatestBackup.'
}
else {
    if (-not [System.IO.Path]::IsPathRooted($BackupFile)) {
        $BackupFile = [System.IO.Path]::GetFullPath((Join-Path -Path (Get-Location).Path -ChildPath $BackupFile))
    }
    else {
        $BackupFile = [System.IO.Path]::GetFullPath($BackupFile)
    }
}

$backupInfo = Test-PlainSqlDumpFile -Path $BackupFile

try {
    $null = Get-Command $PsqlPath -ErrorAction Stop
}
catch {
    throw "psql not found. Install PostgreSQL client tools or pass -PsqlPath."
}

$useSudo = $UseLinuxSudoPostgres.IsPresent
if (-not $useSudo -and $platform.IsLinux -and $UserName -eq 'postgres' -and ($HostName -eq 'localhost' -or $HostName -eq '127.0.0.1')) {
    $useSudo = $true
    $warnings.Add('Auto-enabled -UseLinuxSudoPostgres on Linux for postgres@localhost (stdin redirect avoids -f permission errors).')
}

if (-not $useSudo -and $platform.IsLinux -and $UserName -eq 'postgres') {
    $warnings.Add('If restore fails with "Permission denied" on -f, re-run with -UseLinuxSudoPostgres.')
}

$restoreMethod = if ($useSudo) { 'Linux: sudo -u postgres psql + stdin redirect' } else { 'Direct: psql stdin stream' }

if (-not $SkipPasswordPrompt -and -not $useSudo) {
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
elseif ($useSudo -and -not $SkipPasswordPrompt) {
    Write-Host "Using sudo -u postgres (peer auth). You may be prompted for your Linux password." -ForegroundColor DarkGray
}

if ($RecreateDatabase) {
    Confirm-DestructiveRestore -Database $DatabaseName -Force:$Force
    Invoke-RecreateDatabase -ExecutablePath $PsqlPath -Database $DatabaseName -User $UserName `
        -DbHost $HostName -DbPort $Port -AdminDatabase $AdminDatabase -UseLinuxSudoPostgres:$useSudo
}
elseif ($CreateDatabaseIfMissing) {
    Invoke-CreateDatabaseIfMissing -ExecutablePath $PsqlPath -Database $DatabaseName -User $UserName `
        -DbHost $HostName -DbPort $Port -AdminDatabase $AdminDatabase -UseLinuxSudoPostgres:$useSudo
}
else {
    if (-not (Test-DatabaseExists -ExecutablePath $PsqlPath -Database $DatabaseName -User $UserName `
                -DbHost $HostName -DbPort $Port -AdminDatabase $AdminDatabase -UseLinuxSudoPostgres:$useSudo)) {
        throw "Database '$DatabaseName' does not exist. Use -CreateDatabaseIfMissing or -RecreateDatabase."
    }
}

$started = Get-Date
try {
    $null = Invoke-PlainSqlRestore -ExecutablePath $PsqlPath -BackupFilePath $BackupFile `
        -Database $DatabaseName -User $UserName -DbHost $HostName -DbPort $Port -UseLinuxSudoPostgres:$useSudo
}
finally {
    Remove-PgPasswordEnv
}
$duration = (Get-Date) - $started

$metrics = [ordered]@{}
$queryResult = Invoke-PsqlMetricsQuery -ExecutablePath $PsqlPath -Database $DatabaseName -User $UserName `
    -DbHost $HostName -DbPort $Port -UseLinuxSudoPostgres:$useSudo
if ($queryResult.ExitCode -ne 0) {
    $warnings.Add('Post-restore metrics query failed; summary may be incomplete.')
}
else {
    foreach ($line in $queryResult.Output) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split '\|', 2
        if ($parts.Count -eq 2) {
            $metrics[$parts[0]] = $parts[1]
        }
    }
}

$tableCount = Get-MetricValueOrDefault -Metrics $metrics -Key 'table_count'
if ($tableCount -eq '0' -or $tableCount -eq 'N/A') {
    $warnings.Add("Post-restore table count is '$tableCount'. Verify the dump restored into the correct database.")
}

Write-RestoreSummary -BackupInfo $backupInfo -Project $ProjectName -Database $DatabaseName -User $UserName `
    -DbHost $HostName -DbPort $Port -RestoreMethod $restoreMethod -Duration $duration `
    -Metrics $metrics -Warnings $warnings
