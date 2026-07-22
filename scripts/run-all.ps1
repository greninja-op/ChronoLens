# Local one-command launcher (Windows): demo store + Mission Control + load stream.
# Assumes SigNoz is already up (WSL: bash scripts/bringup.sh) and .env has SIGNOZ_API_KEY.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONPATH = "src"
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "==> demo store -> :8090" -ForegroundColor Cyan
$store = Start-Process -PassThru -NoNewWindow $py "-m demo_store.store"
Start-Sleep 3
Write-Host "==> Mission Control -> http://localhost:8095" -ForegroundColor Cyan
$app = Start-Process -PassThru -NoNewWindow $py "app.py"
Start-Sleep 2
Write-Host "==> load generator (gentle)" -ForegroundColor Cyan
$load = Start-Process -PassThru -NoNewWindow $py "scripts\loadgen.py 300"

Write-Host "`nAll up. Open http://localhost:8095  (close this window to stop)" -ForegroundColor Green
try { Wait-Process -Id $app.Id }
finally { $store, $app, $load | ForEach-Object { try { Stop-Process -Id $_.Id -Force } catch {} } }
