# Vendor the chronolens package into the Lambda source dir (Windows).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $root "src\chronolens"
$dst = Join-Path $root "infra\lambda\chronolens"

Write-Host "==> vendoring chronolens -> infra/lambda/chronolens" -ForegroundColor Cyan
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item -Recurse -Force "$src\*" $dst -Exclude "__pycache__"
Get-ChildItem -Recurse -Directory -Filter __pycache__ $dst | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "done. Next: cd infra; sam build; sam deploy --guided" -ForegroundColor Green
