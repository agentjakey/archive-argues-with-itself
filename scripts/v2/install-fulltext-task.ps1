# Registers (or replaces) the Windows scheduled tasks that keep the laptop's long jobs running: each
# starts its service script at logon, hidden, for the current user, and starts it now.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\v2\install-fulltext-task.ps1               # the full-text fetch
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\v2\install-fulltext-task.ps1 -Job builder  # the shard builder
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\v2\install-fulltext-task.ps1 [-Job builder] -Remove
param([ValidateSet("fetch", "builder")][string]$Job = "fetch", [switch]$Remove)
$Jobs = @{
    fetch   = @{ Name = "ArchiveArgues-FullTextFetch"; Script = "fulltext-service.ps1";
                 Description = "Archive Argues: full-text fetch from archive.org (resumes from its R2 state)" }
    builder = @{ Name = "ArchiveArgues-ShardBuilder"; Script = "shard-builder-service.ps1";
                 Description = "Archive Argues: builds engine shards as their text arrives (heavy lock, memory and disk floors)" }
}
$Name = $Jobs[$Job].Name
if ($Remove) {
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    "removed $Name (a running pass keeps going until it is stopped)"
    exit 0
}
$Script = Join-Path $PSScriptRoot $Jobs[$Job].Script
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Script`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description $Jobs[$Job].Description -Force | Out-Null
Start-ScheduledTask -TaskName $Name
Get-ScheduledTask -TaskName $Name | Select-Object TaskName, State
