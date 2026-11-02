# Registers (or replaces) the Windows scheduled task that keeps the full-text fetch running:
# it starts fulltext-service.ps1 at logon, hidden, for the current user, and starts it now.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\v2\install-fulltext-task.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\v2\install-fulltext-task.ps1 -Remove
param([switch]$Remove)
$Name = "ArchiveArgues-FullTextFetch"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    "removed $Name (a running pass keeps going until it is stopped)"
    exit 0
}
$Script = Join-Path $PSScriptRoot "fulltext-service.ps1"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Script`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Archive Argues: full-text fetch from archive.org (resumes from its R2 state)" -Force | Out-Null
Start-ScheduledTask -TaskName $Name
Get-ScheduledTask -TaskName $Name | Select-Object TaskName, State
