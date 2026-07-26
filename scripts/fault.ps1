# Inject (or clear) a fault in the demo store — the one command the demo beats need.
#
# Why this exists: in PowerShell 5.1 `curl` is an alias for Invoke-WebRequest, so the
# curl syntax in the docs (`curl -X POST "...?a=b&c=d"`) fails twice over — the flags
# aren't understood, and an unquoted `&` is a PowerShell operator. This wrapper takes
# the arguments properly so there's nothing to get wrong on camera.
#
# Usage (from the chronolens/ folder):
#
#     .\scripts\fault.ps1 dependency     # blast-radius beat  (dependency-slow, level 40)
#     .\scripts\fault.ps1 ramp           # loop / Chrono-Proof beats (traffic-ramp, level 12)
#     .\scripts\fault.ps1 off            # clear it
#
#     .\scripts\fault.ps1 -Mode pool-leak -Level 25     # anything else the store supports
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('dependency', 'ramp', 'off', 'custom')]
    [string]$Preset = 'dependency',

    [string]$Mode = '',
    [int]$Level = -1,
    [string]$StoreUrl = $env:DEMO_STORE_URL
)

if (-not $StoreUrl) { $StoreUrl = 'http://localhost:8090' }

switch ($Preset) {
    'dependency' { if (-not $Mode) { $Mode = 'dependency-slow' }; if ($Level -lt 0) { $Level = 40 } }
    'ramp'       { if (-not $Mode) { $Mode = 'traffic-ramp' };    if ($Level -lt 0) { $Level = 12 } }
    'off'        { $Mode = 'off';  $Level = 0 }
    'custom'     { if (-not $Mode) { throw 'custom needs -Mode' }; if ($Level -lt 0) { $Level = 10 } }
}

$uri = "$StoreUrl/admin/fault?mode=$Mode&level=$Level"
try {
    # NOTE: /admin/fault is a GET endpoint (see demo_store/store.py). POSTing it
    # returns 405 — which is exactly what the old `curl -X POST` line in the docs did.
    $resp = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec 10
    Write-Host "fault -> mode=$Mode level=$Level  ($StoreUrl)" -ForegroundColor Green
    $resp | ConvertTo-Json -Depth 4
    if ($Mode -eq 'dependency-slow') {
        Write-Host "`nWait ~60s before the blast-radius beat, so SigNoz's service map catches up." -ForegroundColor Yellow
    } elseif ($Mode -eq 'traffic-ramp') {
        Write-Host "`nWait ~90s for p99 to climb toward the SLO before running the loop." -ForegroundColor Yellow
    }
} catch {
    Write-Host "failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "is the demo store up on $StoreUrl ?" -ForegroundColor Red
    exit 1
}
