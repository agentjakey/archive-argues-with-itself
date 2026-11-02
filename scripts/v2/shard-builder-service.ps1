# Runs the shard builder (scripts/v2/shard_builder.py run) until every shard is built, across reboots.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\v2\shard-builder-service.ps1
#
# install-fulltext-task.ps1 -Job builder registers it as a scheduled task at logon. One instance at a
# time. The builder itself waits for the heavy lock, free memory and free disk before each shard, and
# resumes from data\build\state.json and the shard manifests on R2. After a crash it starts again in
# five minutes. Log: data\build\builder.log and data\build\service.log.
$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Python = $env:ARCHIVE_ARGUES_PYTHON
if (-not $Python) { $Python = "C:\Users\profe\OneDrive\Desktop\python\archive-argues-with-itself\.venv\Scripts\python.exe" }
$Data = Join-Path $Repo "data\build"
New-Item -ItemType Directory -Force $Data | Out-Null
$Log = Join-Path $Data "service.log"
$PidFile = Join-Path $Data "service.pid"

function Write-Log([string]$Text) {
    "$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) $Text" | Out-File -Append -Encoding ascii $Log
}

if (Test-Path $PidFile) {
    $Other = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($Other -and (Get-Process -Id $Other -ErrorAction SilentlyContinue)) {
        Write-Log "another builder service ($Other) is running; exiting"
        exit 0
    }
}
$PID | Out-File -Encoding ascii $PidFile
Set-Location $Repo
$env:PYTHONPATH = "src"
while ($true) {
    Write-Log "builder starting"
    & $Python scripts/v2/shard_builder.py run *>> (Join-Path $Data "run.log")
    $Code = $LASTEXITCODE
    Write-Log "builder ended with exit code $Code"
    if ($Code -eq 0) { break }
    Start-Sleep -Seconds 300
}
Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
