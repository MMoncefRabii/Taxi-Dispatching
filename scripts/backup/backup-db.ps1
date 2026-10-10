[CmdletBinding()]
param(
    [string]$BackupDir = 'C:\td-backups',
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'

function Get-PostgresContainerId {
    param([string]$ComposeFile)

    $output = Invoke-DockerCommand `
        -Arguments @('compose', '-f', $ComposeFile, 'ps', '-q', 'postgres') `
        -FailureMessage 'Could not locate the postgres container'
    $containerId = ($output | Out-String).Trim()
    if (-not $containerId) {
        throw 'The postgres container is not running; start it with docker compose up -d postgres.'
    }
    return $containerId
}

function Invoke-DockerCommand {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments,
        [Parameter(Mandatory)]
        [string]$FailureMessage
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = @(& docker @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        foreach ($line in $output) {
            [Console]::Error.WriteLine($line.ToString())
        }
        throw "$FailureMessage (docker exit code $exitCode)."
    }

    return ,$output
}

function Invoke-Retention {
    param([string]$Directory, [switch]$Preview)

    $dumps = @(
        Get-ChildItem -LiteralPath $Directory -File -Filter 'fleet_*.dump' |
            Where-Object { $_.Name -match '^fleet_\d{8}_\d{6}\.dump$' } |
            ForEach-Object {
                $dateText = $_.BaseName.Substring(6)
                $date = [datetime]::MinValue
                $validDate = [datetime]::TryParseExact(
                    $dateText,
                    'yyyyMMdd_HHmmss',
                    [Globalization.CultureInfo]::InvariantCulture,
                    [Globalization.DateTimeStyles]::None,
                    [ref]$date
                )
                if ($validDate) {
                    [PSCustomObject]@{ File = $_; Date = $date }
                }
            }
    )
    $keep = [System.Collections.Generic.HashSet[string]]::new(
        [StringComparer]::OrdinalIgnoreCase
    )
    foreach ($entry in ($dumps | Sort-Object Date -Descending | Select-Object -First 14)) {
        [void]$keep.Add($entry.File.FullName)
    }
    foreach (
        $entry in (
            $dumps |
                Where-Object { $_.Date.DayOfWeek -eq [DayOfWeek]::Sunday } |
                Sort-Object Date -Descending |
                Select-Object -First 8
        )
    ) {
        [void]$keep.Add($entry.File.FullName)
    }

    foreach ($entry in $dumps) {
        if ($keep.Contains($entry.File.FullName)) {
            continue
        }
        $relatedFiles = @($entry.File)
        $checksumPath = "$($entry.File.FullName).sha256"
        if (Test-Path -LiteralPath $checksumPath -PathType Leaf) {
            $relatedFiles += Get-Item -LiteralPath $checksumPath
        }
        foreach ($file in $relatedFiles) {
            if ($Preview) {
                Write-Output "WhatIf: would delete $($file.FullName)"
            }
            else {
                Remove-Item -LiteralPath $file.FullName -Force
                Write-Output "Deleted $($file.FullName)"
            }
        }
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path.TrimEnd('\')
$repoPrefix = "$repoRoot\"
$resolvedBackupDir = [IO.Path]::GetFullPath($BackupDir).TrimEnd('\')
if (
    $resolvedBackupDir.Equals($repoRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $resolvedBackupDir.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)
) {
    Write-Error 'BACKUP_DIR must not be inside the Git repository.'
    exit 1
}

$localDumpPath = $null
$checksumPath = $null
$backupComplete = $false
$remoteDumpPath = "/tmp/fleet_backup_$([guid]::NewGuid().ToString('N')).dump"
$containerId = $null
try {
    [void][IO.Directory]::CreateDirectory($resolvedBackupDir)
    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $localDumpPath = Join-Path $resolvedBackupDir "fleet_$timestamp.dump"
    $checksumPath = "$localDumpPath.sha256"
    if (Test-Path -LiteralPath $localDumpPath) {
        throw "A backup already exists for timestamp $timestamp; refusing to overwrite it."
    }

    $composeFile = Join-Path $repoRoot 'backend\docker-compose.yml'
    $containerId = Get-PostgresContainerId -ComposeFile $composeFile
    $databaseUserOutput = Invoke-DockerCommand `
        -Arguments @('exec', $containerId, 'printenv', 'POSTGRES_USER') `
        -FailureMessage 'Could not read POSTGRES_USER from the postgres container'
    $databaseUser = ($databaseUserOutput | Out-String).Trim()
    if (-not $databaseUser) {
        throw 'POSTGRES_USER is empty in the postgres container.'
    }
    $databaseNameOutput = Invoke-DockerCommand `
        -Arguments @('exec', $containerId, 'printenv', 'POSTGRES_DB') `
        -FailureMessage 'Could not read POSTGRES_DB from the postgres container'
    $databaseName = ($databaseNameOutput | Out-String).Trim()
    if (-not $databaseName) {
        throw 'POSTGRES_DB is empty in the postgres container.'
    }

    [void](Invoke-DockerCommand `
        -Arguments @('exec', $containerId, 'pg_dump', '-U', $databaseUser, '-Fc', '-f', $remoteDumpPath, $databaseName) `
        -FailureMessage 'pg_dump failed inside the postgres container')
    [void](Invoke-DockerCommand `
        -Arguments @('exec', $containerId, 'pg_restore', '--list', $remoteDumpPath) `
        -FailureMessage 'pg_restore --list could not read the dump inside the postgres container')

    [void](Invoke-DockerCommand `
        -Arguments @('cp', "${containerId}:$remoteDumpPath", $localDumpPath) `
        -FailureMessage 'Could not copy the verified dump out of the postgres container')
    if (-not (Test-Path -LiteralPath $localDumpPath -PathType Leaf) -or
        (Get-Item -LiteralPath $localDumpPath).Length -le 0) {
        throw 'The copied dump is missing or empty.'
    }

    [void](Invoke-DockerCommand `
        -Arguments @('exec', $containerId, 'rm', '-f', $remoteDumpPath) `
        -FailureMessage 'Could not remove the temporary dump from the postgres container')
    $remoteDumpPath = $null

    $hash = (Get-FileHash -LiteralPath $localDumpPath -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText(
        $checksumPath,
        "$hash  $([IO.Path]::GetFileName($localDumpPath))`n",
        [Text.Encoding]::ASCII
    )
    $backupComplete = $true
    Write-Output "Backup created: $localDumpPath"
    Write-Output "Checksum created: $checksumPath"
    Invoke-Retention -Directory $resolvedBackupDir -Preview:$WhatIf
}
catch {
    if (-not $backupComplete -and $localDumpPath -and
        (Test-Path -LiteralPath $localDumpPath -PathType Leaf)) {
        Remove-Item -LiteralPath $localDumpPath -Force -ErrorAction SilentlyContinue
    }
    if (-not $backupComplete -and $checksumPath -and
        (Test-Path -LiteralPath $checksumPath -PathType Leaf)) {
        Remove-Item -LiteralPath $checksumPath -Force -ErrorAction SilentlyContinue
    }
    Write-Error "Database backup failed: $($_.Exception.Message)"
    exit 1
}
finally {
    if ($containerId -and $remoteDumpPath) {
        try {
            [void](Invoke-DockerCommand `
                -Arguments @('exec', $containerId, 'rm', '-f', $remoteDumpPath) `
                -FailureMessage 'Could not remove the temporary dump from the postgres container')
        }
        catch {
            Write-Warning $_.Exception.Message
            if ($backupComplete) {
                exit 1
            }
        }
    }
}
