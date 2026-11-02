# Runs the full-text fetch until the whole collection is fetched, from any state, across reboots.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\v2\fulltext-service.ps1
#
# The Windows scheduled task made by install-fulltext-task.ps1 starts this at logon. One instance
# at a time: a second copy exits when the first is alive. Each pass runs
# `python scripts/v2/catalogue.py fulltext`, which resumes from its manifest (rebuilt from R2 when
# the local copy is missing). After a pass that stopped on repeated 429/503 it waits an hour; after a
# crash, five minutes; after a pass that finished with nothing left to fetch, it exits.
# Log: data\fulltext\service.log. Status: python scripts\v2\catalogue.py status
$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Python = $env:ARCHIVE_ARGUES_PYTHON
if (-not $Python) { $Python = "C:\Users\profe\OneDrive\Desktop\python\archive-argues-with-itself\.venv\Scripts\python.exe" }
$Data = Join-Path $Repo "data\fulltext"
New-Item -ItemType Directory -Force $Data | Out-Null
$Log = Join-Path $Data "service.log"
$PidFile = Join-Path $Data "service.pid"

function Write-Log([string]$Text) {
    "$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) $Text" | Out-File -Append -Encoding ascii $Log
}

if (Test-Path $PidFile) {
    $Other = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($Other -and (Get-Process -Id $Other -ErrorAction SilentlyContinue)) {
        Write-Log "another service instance ($Other) is running; exiting"
        exit 0
    }
}
$PID | Out-File -Encoding ascii $PidFile

Set-Location $Repo
$env:PYTHONPATH = "src"
while ($true) {
    Write-Log "pass starting"
    & $Python scripts/v2/catalogue.py fulltext *>> (Join-Path $Data "run.log")
    $Code = $LASTEXITCODE
    $Line = & $Python scripts/v2/catalogue.py status 2>&1
    Write-Log "pass ended with exit code $Code; $Line"
    if ($Code -eq 0) {
        $Status = Get-Content (Join-Path $Data "status.json") -Raw | ConvertFrom-Json
        if ($Status.remaining -eq 0) {
            Write-Log "nothing left to fetch; exiting"
            break
        }
        Start-Sleep -Seconds 300      # items that failed are tried again on the next pass
    } elseif ($Code -eq 1) {
        Write-Log "stopped on repeated 429/503: waiting an hour"
        Start-Sleep -Seconds 3600
    } else {
        Start-Sleep -Seconds 300
    }
}
Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
