#Requires -Version 5.1
# ======================================================
# Remote DB backup via SSH tunnel (Step 2)
# ======================================================
# Opens:  ssh -L <LocalTunnelPort>:<RemotePgHost>:<RemotePgPort> <SshUser>@<SshHost> -N
# Then runs full_manual_db_backup_script.ps1 against localhost:<LocalTunnelPort>.
#
# Passwords (do not put them in this file):
#   PostgreSQL — prompted when the script runs, unless you use -SkipPasswordPrompt
#     with PGPASSWORD set in the shell:  export PGPASSWORD='your_db_password'
#   SSH — use -SshIdentityFile ~/.ssh/your_key, or start the tunnel yourself and use
#     -SkipSshTunnel (ssh will ask for its password in that terminal).
#
# Example:
#   pwsh ./backup_db_via_ssh_tunnel.ps1
#   export PGPASSWORD='your_db_password'
#   pwsh ./backup_db_via_ssh_tunnel.ps1 -SkipPasswordPrompt -SshIdentityFile ~/.ssh/id_rsa
#
# If you already have a tunnel (e.g. ssh -L 5433:localhost:5432 ...):
#   pwsh ./backup_db_via_ssh_tunnel.ps1 -SkipSshTunnel

[CmdletBinding()]
param(
    # SSH / tunnel
    [Parameter()][string]$SshHost = '13.234.142.190',
    [Parameter()][string]$SshUser = 'citpladmin',
    [Parameter()][string]$SshExecutable = 'ssh',
    [Parameter()][string]$SshIdentityFile = '',
    [Parameter()][string[]]$SshExtraArgs = @(),
    [Parameter()][switch]$SkipSshTunnel,

    # Remote PostgreSQL endpoint (as seen from the SSH server)
    [Parameter()][string]$RemotePgHost = 'localhost',
    [Parameter()][ValidateRange(1, 65535)][int]$RemotePgPort = 5432,
    [Parameter()][ValidateRange(1, 65535)][int]$LocalTunnelPort = 5433,
    [Parameter()][ValidateRange(1, 120)][int]$TunnelReadyTimeoutSeconds = 30,

    # Passed through to full_manual_db_backup_script.ps1
    [Parameter()][string]$ProjectName = 'kaizen',
    [Parameter()][string]$DatabaseName = 'kaizen_dev',
    [Parameter()][string]$UserName = 'praveena',
    [Parameter()][string]$BackupDirectory = './backups',
    [Parameter()][string]$PgDumpPath = 'pg_dump',
    [Parameter()][string]$PsqlPath = 'psql',
    [Parameter()][ValidateRange(0, 3650)][int]$RetentionDays = 0,
    [Parameter()][switch]$SkipPasswordPrompt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$backupScriptPath = Join-Path -Path $PSScriptRoot -ChildPath 'full_manual_db_backup_script.ps1'
if (-not (Test-Path -LiteralPath $backupScriptPath)) {
    throw "Backup script not found: $backupScriptPath"
}

function Test-TcpPortOpen {
    param(
        [string]$TargetHost,
        [int]$TargetPort,
        [int]$TimeoutMs = 2000
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($TargetHost, $TargetPort)
        if (-not $task.Wait($TimeoutMs)) {
            return $false
        }
        return $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Wait-TunnelReady {
    param(
        [int]$Port,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPortOpen -TargetHost '127.0.0.1' -TargetPort $Port) {
            return
        }
        Start-Sleep -Milliseconds 500
    }

    throw "SSH tunnel did not become ready on 127.0.0.1:${Port} within ${TimeoutSeconds}s. Check SSH access and that PostgreSQL is listening on the remote host."
}

function Start-SshTunnel {
    param(
        [string]$Executable,
        [string]$User,
        [string]$HostName,
        [string]$IdentityFile,
        [string[]]$ExtraArgs,
        [string]$PgHost,
        [int]$PgPort,
        [int]$LocalPort
    )

    if (Test-TcpPortOpen -TargetHost '127.0.0.1' -TargetPort $LocalPort) {
        Write-Host "Port $LocalPort is already in use on localhost; assuming an existing tunnel." -ForegroundColor Yellow
        return $null
    }

    $forward = "${LocalPort}:${PgHost}:${PgPort}"
    $sshArgs = @(
        '-N'
        '-o', 'ExitOnForwardFailure=yes'
        '-o', 'ServerAliveInterval=30'
        '-L', $forward
    )

    if (-not [string]::IsNullOrWhiteSpace($IdentityFile)) {
        $sshArgs += @('-i', $IdentityFile)
    }

    if ($ExtraArgs -and $ExtraArgs.Count -gt 0) {
        $sshArgs += $ExtraArgs
    }

    $sshArgs += "${User}@${HostName}"

    Write-Host "Starting SSH tunnel: $Executable $($sshArgs -join ' ')" -ForegroundColor Cyan

    $startParams = @{
        FilePath     = $Executable
        ArgumentList = $sshArgs
        PassThru     = $true
    }
    if ($IsWindows) {
        $startParams['WindowStyle'] = 'Hidden'
    }

    $process = Start-Process @startParams

    if ($null -eq $process) {
        throw 'Failed to start ssh process.'
    }

    Start-Sleep -Seconds 1
    if ($process.HasExited) {
        throw "SSH exited immediately (code $($process.ExitCode)). Verify host, user, and key/password access."
    }

    return $process
}

function Stop-SshTunnel {
    param([System.Diagnostics.Process]$Process)

    if ($null -eq $Process) {
        return
    }

    if (-not $Process.HasExited) {
        Write-Host 'Stopping SSH tunnel...' -ForegroundColor DarkGray
        $Process.Kill()
        $Process.WaitForExit(5000) | Out-Null
    }
}

function Remove-PgPasswordEnv {
    if (Test-Path Env:PGPASSWORD) {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
}

function Set-PgPasswordFromSecureString {
    param([System.Security.SecureString]$SecurePassword)

    if ($null -eq $SecurePassword -or $SecurePassword.Length -eq 0) {
        return
    }

    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
    try {
        $env:PGPASSWORD = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function Initialize-DbPassword {
    param([ref]$SkipPrompt)

    if ($SkipPrompt.Value) {
        if ([string]::IsNullOrWhiteSpace($env:PGPASSWORD)) {
            Write-Warning 'SkipPasswordPrompt is set but PGPASSWORD is empty; pg_dump may fail.'
        }
        return
    }

    if (-not [string]::IsNullOrWhiteSpace($env:PGPASSWORD)) {
        $SkipPrompt.Value = $true
        return
    }

    $securePwd = Read-Host -AsSecureString "PostgreSQL password for user '$UserName' (leave empty if not required)"
    Set-PgPasswordFromSecureString -SecurePassword $securePwd
    if (-not [string]::IsNullOrWhiteSpace($env:PGPASSWORD)) {
        $SkipPrompt.Value = $true
    }
}

$sshProcess = $null
$skipDbPasswordPrompt = [bool]$SkipPasswordPrompt

try {
    Initialize-DbPassword -SkipPrompt ([ref]$skipDbPasswordPrompt)
    if (-not $SkipSshTunnel) {
        $sshProcess = Start-SshTunnel `
            -Executable $SshExecutable `
            -User $SshUser `
            -HostName $SshHost `
            -IdentityFile $SshIdentityFile `
            -ExtraArgs $SshExtraArgs `
            -PgHost $RemotePgHost `
            -PgPort $RemotePgPort `
            -LocalPort $LocalTunnelPort

        if ($null -ne $sshProcess) {
            Wait-TunnelReady -Port $LocalTunnelPort -TimeoutSeconds $TunnelReadyTimeoutSeconds
            Write-Host "Tunnel ready: localhost:$LocalTunnelPort -> ${RemotePgHost}:${RemotePgPort} on $SshHost" -ForegroundColor Green
        }
    }
    else {
        Write-Host "Skipping SSH tunnel; using existing localhost:$LocalTunnelPort" -ForegroundColor Yellow
        if (-not (Test-TcpPortOpen -TargetHost '127.0.0.1' -TargetPort $LocalTunnelPort)) {
            throw "No listener on 127.0.0.1:${LocalTunnelPort}. Start a tunnel first or omit -SkipSshTunnel."
        }
    }

    $backupArgs = @{
        ProjectName          = $ProjectName
        DatabaseName         = $DatabaseName
        UserName             = $UserName
        HostName             = 'localhost'
        Port                 = $LocalTunnelPort
        BackupDirectory      = $BackupDirectory
        PgDumpPath           = $PgDumpPath
        PsqlPath             = $PsqlPath
        RetentionDays        = $RetentionDays
    }

    if ($skipDbPasswordPrompt) {
        $backupArgs['SkipPasswordPrompt'] = $true
    }

    & $backupScriptPath @backupArgs

    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Stop-SshTunnel -Process $sshProcess
    Remove-PgPasswordEnv
}
