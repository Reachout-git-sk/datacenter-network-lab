# Capture the provisioned Grafana dashboard with headless Microsoft Edge (Windows).
#   powershell -File scripts\grafana-screenshot.ps1 [-Out docs\img\grafana-dc-fabric.png] [-From now-15m]
param(
  [string]$Out = "docs\img\grafana-dc-fabric.png",
  [string]$From = "now-15m",
  [int]$Width = 1600,
  [int]$Height = 1450,
  [string]$Url = "http://localhost:3000/d/dc-fabric"
)
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$outPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Out))
$profileDir = Join-Path $env:TEMP "dclab-edge-headless"
$target = "$Url" + "?orgId=1&kiosk&from=$From&to=now&refresh=1h"
$p = Start-Process -FilePath $edge -PassThru -Wait -RedirectStandardError (Join-Path $env:TEMP "dclab-edge.log") -ArgumentList @(
  "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
  "--user-data-dir=$profileDir", "--window-size=$Width,$Height",
  "--virtual-time-budget=15000", "--screenshot=$outPath", $target)
if (Test-Path $outPath) { Write-Output "saved $outPath" } else { Write-Error "screenshot failed (exit $($p.ExitCode))"; exit 1 }
