param(
  [string]$Exe        = "C:\Program Files\NVIDIA Corporation\FrameViewSDK\bin\PresentMon_x64.exe",
  [string]$Process    = "helldivers2.exe",
  [string]$Csv        = "C:\Users\Public\presentmon_hd2.csv",
  [switch]$Foreground,           # If set, run in the current window; otherwise background
  [switch]$AddPerfLogUsers       # If set, add current user to Performance Log Users
)

$ErrorActionPreference = "Stop"

if ($AddPerfLogUsers) {
  Write-Host "Adding $env:USERNAME to 'Performance Log Users'..." -ForegroundColor Cyan
  net localgroup "Performance Log Users" "$env:USERNAME" /add | Out-Null
  Write-Host "Done. Sign out/in (or reboot) for group change to take effect." -ForegroundColor Yellow
}

if (-not (Test-Path $Exe)) { throw "PresentMon not found at: $Exe" }
$csvDir = Split-Path $Csv -Parent
if (-not (Test-Path $csvDir)) { New-Item -ItemType Directory -Force -Path $csvDir | Out-Null }

# Build args cleanly so no quote/backtick weirdness
$pmArgs = @(
  '--process_name', $Process,
  '--output_file',  $Csv,
  '--v2_metrics',
  '--terminate_on_proc_exit',
  '--stop_existing_session'
)

if ($Foreground) {
  Write-Host "Starting PresentMon in foreground..." -ForegroundColor Green
  & $Exe @pmArgs
} else {
  Write-Host "Starting PresentMon in background..." -ForegroundColor Green
  Start-Process -FilePath $Exe -ArgumentList $pmArgs -WindowStyle Hidden | Out-Null
}

Write-Host "Writing to: $Csv"
Write-Host "PresentMon will exit automatically when $Process closes."

## Run normally (background): 
# .\run_presentmon_hd2.ps1

## Run in foreground (shows output in your console): 
# .\run_presentmon_hd2.ps1 -Foreground

## Fix permissions (once), then sign out/in: 
# .\run_presentmon_hd2.ps1 -AddPerfLogUsers

## Watch the CSV live: 
# Get-Content "C:\Users\Public\presentmon_hd2.csv" -Tail 5 -Wait

## Force Stop: 
# Get-Process PresentMon_x64 -ErrorAction SilentlyContinue | Stop-Process -Force