[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidatePattern('^(?:[01]\d|2[0-3]):[0-5]\d$')]
    [string]$Time = '02:00',
    [switch]$Unregister
)

$ErrorActionPreference = 'Stop'
$taskName = 'FleetBackup'

try {
    if ($Unregister) {
        if ($PSCmdlet.ShouldProcess($taskName, 'Unregister scheduled task')) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
            Write-Output "Unregistered scheduled task $taskName."
        }
        exit 0
    }

    $backupScript = Join-Path $PSScriptRoot 'backup-db.ps1'
    $action = New-ScheduledTaskAction `
        -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$backupScript`""
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel Limited
    if ($PSCmdlet.ShouldProcess($taskName, "Register daily backup at $Time")) {
        Register-ScheduledTask `
            -TaskName $taskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Principal $principal `
            -Description 'Create a verified local Fleet PostgreSQL backup.' `
            -Force | Out-Null
        Write-Output "Registered $taskName daily at $Time. It runs only when this PC and Docker Desktop are available."
    }
}
catch {
    Write-Error "Scheduled task operation failed: $($_.Exception.Message)"
    exit 1
}
