[CmdletBinding()]
param(
    [string]$DumpPath,
    [string]$BackupDir = 'C:\td-backups',
    [ValidateRange(0, 1000000)]
    [int]$DriverLocationsTolerance = 0
)

$ErrorActionPreference = 'Stop'
$testDatabase = 'fleet_restore_test'
$tableNames = @('drivers', 'driver_locations', 'admins', 'centers', 'vehicles')
$countQuery = "SELECT 'drivers', COUNT(*) FROM public.drivers UNION ALL SELECT 'driver_locations', COUNT(*) FROM public.driver_locations UNION ALL SELECT 'admins', COUNT(*) FROM public.admins UNION ALL SELECT 'centers', COUNT(*) FROM public.centers UNION ALL SELECT 'vehicles', COUNT(*) FROM public.vehicles"

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

if ($testDatabase -cne 'fleet_restore_test') {
    Write-Error 'The restore-test database name must remain fleet_restore_test.'
    exit 1
}

$containerId = $null
$remoteDumpPath = $null
$testDatabaseMayExist = $false
$cleanupFailed = $false
try {
    if (-not $DumpPath) {
        $candidate = Get-ChildItem -LiteralPath $BackupDir -File -Filter 'fleet_*.dump' |
            Where-Object { $_.Name -match '^fleet_\d{8}_\d{6}\.dump$' } |
            Sort-Object Name -Descending |
            Select-Object -First 1
        if (-not $candidate) {
            throw "No fleet_YYYYMMDD_HHmmss.dump backup was found in '$BackupDir'."
        }
        $DumpPath = $candidate.FullName
    }
    $resolvedDumpPath = (Resolve-Path -LiteralPath $DumpPath).Path
    if ((Get-Item -LiteralPath $resolvedDumpPath).Length -le 0) {
        throw 'The selected dump is empty.'
    }

    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
    $composeFile = Join-Path $repoRoot 'backend\docker-compose.yml'
    $containerId = Get-PostgresContainerId -ComposeFile $composeFile
    $remoteDumpPath = "/tmp/fleet_restore_test_$([guid]::NewGuid().ToString('N')).dump"
    [void](Invoke-DockerCommand `
        -Arguments @('cp', $resolvedDumpPath, "${containerId}:$remoteDumpPath") `
        -FailureMessage 'Could not copy the selected dump into the postgres container')

    $databaseUserOutput = Invoke-DockerCommand `
        -Arguments @('exec', $containerId, 'printenv', 'POSTGRES_USER') `
        -FailureMessage 'Could not read POSTGRES_USER from the postgres container'
    $databaseUser = ($databaseUserOutput | Out-String).Trim()
    if (-not $databaseUser) {
        throw 'POSTGRES_USER is empty in the postgres container.'
    }
    $liveDatabaseOutput = Invoke-DockerCommand `
        -Arguments @('exec', $containerId, 'printenv', 'POSTGRES_DB') `
        -FailureMessage 'Could not read POSTGRES_DB from the postgres container'
    $liveDatabase = ($liveDatabaseOutput | Out-String).Trim()
    if (-not $liveDatabase) {
        throw 'POSTGRES_DB is empty in the postgres container.'
    }
    if ($liveDatabase -ceq $testDatabase) {
        throw 'The configured live database is fleet_restore_test; refusing to continue.'
    }

    $testDatabaseMayExist = $true
    [void](Invoke-DockerCommand `
        -Arguments @('exec', $containerId, 'dropdb', '--force', '--if-exists', '-U', $databaseUser, $testDatabase) `
        -FailureMessage 'Could not remove the previous fleet_restore_test database')
    [void](Invoke-DockerCommand `
        -Arguments @('exec', $containerId, 'createdb', '-U', $databaseUser, "--owner=$databaseUser", $testDatabase) `
        -FailureMessage 'Could not create fleet_restore_test')
    [void](Invoke-DockerCommand `
        -Arguments @('exec', $containerId, 'pg_restore', '--exit-on-error', '--no-owner', '--no-privileges', '-U', $databaseUser, '-d', $testDatabase, $remoteDumpPath) `
        -FailureMessage 'Could not restore the dump into fleet_restore_test')

    $liveOutput = Invoke-DockerCommand `
        -Arguments @('exec', $containerId, 'psql', '-v', 'ON_ERROR_STOP=1', '-At', '-F', '|', '-U', $databaseUser, '-d', $liveDatabase, '-c', $countQuery) `
        -FailureMessage 'Could not query row counts in the live database'
    $restoredOutput = Invoke-DockerCommand `
        -Arguments @('exec', $containerId, 'psql', '-v', 'ON_ERROR_STOP=1', '-At', '-F', '|', '-U', $databaseUser, '-d', $testDatabase, '-c', $countQuery) `
        -FailureMessage 'Could not query row counts in fleet_restore_test'

    $section = ''
    $counts = @{ Live = @{}; Restored = @{} }
    foreach ($line in $liveOutput) {
        $text = $line.ToString().Trim()
        if ($text -match '^(drivers|driver_locations|admins|centers|vehicles)\|([0-9]+)$') {
            $counts.Live[$Matches[1]] = [long]$Matches[2]
        }
    }
    foreach ($line in $restoredOutput) {
        $text = $line.ToString().Trim()
        if ($text -match '^(drivers|driver_locations|admins|centers|vehicles)\|([0-9]+)$') {
            $counts.Restored[$Matches[1]] = [long]$Matches[2]
        }
    }

    $results = foreach ($table in $tableNames) {
        if (-not $counts.Live.ContainsKey($table) -or
            -not $counts.Restored.ContainsKey($table)) {
            throw "Row counts could not be parsed for '$table'."
        }
        $liveCount = $counts.Live[$table]
        $restoredCount = $counts.Restored[$table]
        $difference = $restoredCount - $liveCount
        $allowedDifference = if ($table -eq 'driver_locations') {
            $DriverLocationsTolerance
        }
        else {
            0
        }
        [PSCustomObject]@{
            Table = $table
            Live = $liveCount
            Restored = $restoredCount
            Difference = $difference
            AllowedDifference = $allowedDifference
            Result = if ([Math]::Abs($difference) -le $allowedDifference) { 'PASS' } else { 'FAIL' }
        }
    }

    $results | Format-Table -AutoSize | Out-String | Write-Output
    $failures = @($results | Where-Object { $_.Result -eq 'FAIL' })
    if ($failures.Count -gt 0) {
        throw 'Row-count mismatch. driver_locations can change while the test runs; use -DriverLocationsTolerance to allow a small difference for that table only.'
    }
    Write-Output "Restore test passed using $resolvedDumpPath."
}
catch {
    Write-Error "Database restore test failed: $($_.Exception.Message)"
    exit 1
}
finally {
    if ($containerId -and $testDatabaseMayExist) {
        try {
            [void](Invoke-DockerCommand `
                -Arguments @('exec', $containerId, 'dropdb', '--force', '--if-exists', '-U', $databaseUser, $testDatabase) `
                -FailureMessage 'Could not remove fleet_restore_test after the restore test')
        }
        catch {
            Write-Warning $_.Exception.Message
            $cleanupFailed = $true
        }
    }
    if ($containerId -and $remoteDumpPath) {
        try {
            [void](Invoke-DockerCommand `
                -Arguments @('exec', $containerId, 'rm', '-f', $remoteDumpPath) `
                -FailureMessage 'Could not remove the temporary dump from the postgres container')
        }
        catch {
            Write-Warning $_.Exception.Message
            $cleanupFailed = $true
        }
    }
    if ($cleanupFailed) {
        exit 1
    }
}
