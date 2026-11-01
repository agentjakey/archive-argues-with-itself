# Start the exhibit on a Windows kiosk: the local server, then Edge in kiosk mode on the exhibit,
# printing silently to the default printer (the receipt printer). Run at sign-in of the kiosk
# account (Task Scheduler, "At log on"). Nothing here needs a network connection.
#
#   powershell -ExecutionPolicy Bypass -File C:\Exhibit\start-kiosk.ps1 -Root C:\Exhibit -Printer
param(
  [string]$Root = "C:\Exhibit",
  [int]$Port = 8765,
  [switch]$Printer
)

$python = Join-Path $Root "python\pythonw.exe"
if (-not (Test-Path $python)) { $python = "pythonw.exe" }
$server = Join-Path $Root "serve.py"
$serverArgs = @($server, "--root", $Root, "--port", $Port)
if ($Printer) { $serverArgs += "--printer" }
Start-Process -FilePath $python -ArgumentList $serverArgs -WindowStyle Hidden

# Wait for the server to answer before opening the browser.
$url = "http://127.0.0.1:$Port/exhibit/"
for ($i = 0; $i -lt 60; $i++) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri ($url + "kiosk.json") -TimeoutSec 2
    if ($r.StatusCode -eq 200) { break }
  } catch { Start-Sleep -Milliseconds 500 }
}

$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) { $edge = "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe" }
# InPrivate: the browser keeps no history, cookies or storage between restarts.
$profile = Join-Path $Root "browser-profile"
$edgeArgs = @(
  "--kiosk", $url,
  "--edge-kiosk-type=fullscreen",
  "--kiosk-printing",
  "--inprivate",
  "--no-first-run",
  "--disable-features=Translate",
  "--user-data-dir=$profile"
)
# A crashed or closed browser comes back: the kiosk always shows the exhibit.
while ($true) {
  $p = Start-Process -FilePath $edge -ArgumentList $edgeArgs -PassThru
  $p.WaitForExit()
  Start-Sleep -Seconds 2
}
