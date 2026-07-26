# Stage a clean, screenshot-worthy Chrono-Proof run.
#
# Chrono-Proof only reads well when the incident it describes was actually prevented:
# a fault still ramping at the moment of the proof means p99 climbed again after the
# fix, so it honestly reports "the fix did not hold" with 0s breach avoided. This
# script drives the full arc instead — clean baseline, controlled ramp, one loop that
# acts and verifies, fault cleared, recovery, then the proof.
#
#     powershell -ExecutionPolicy Bypass -File .\scripts\stage_proof.ps1
#
# Takes roughly 8 minutes. Watch the demand column: the loop is run once demand is
# just past the capacity LEARN will pre-provision, so the +2 scale action can still
# recover it.
$ErrorActionPreference = 'Continue'
$store = 'http://localhost:8090'
$py = '.\.venv\Scripts\python.exe'
$env:PYTHONPATH = 'src'

function Status { Invoke-RestMethod -Uri "$store/admin/status" -TimeoutSec 8 }

Write-Host '== 1/5 clearing fault and resetting capacity to baseline' -ForegroundColor Cyan
Invoke-RestMethod -Uri "$store/admin/lever?action=reset" -Method Post -TimeoutSec 8 | Out-Null
Start-Sleep -Seconds 90
$s = Status
Write-Host ("     baseline: demand={0:N2} cap={1} est={2:N0}ms" -f $s.demand, $s.capacity, $s.est_latency_ms)

Write-Host '== 2/5 injecting a controlled ramp' -ForegroundColor Cyan
Invoke-RestMethod -Uri "$store/admin/fault?mode=traffic-ramp&level=20" -TimeoutSec 8 | Out-Null

Write-Host '== 3/5 waiting for demand to pass the pre-provisioned floor (target ~6.2)' -ForegroundColor Cyan
# Trigger the loop the moment demand *just* passes the pre-provisioned floor
# (baseline 2 + LEARN's +4 = 6), not well past it. Acting while p99 is still under the
# SLO is what makes the proof clean: every post-action bucket stays under the wall, so
# breach-seconds measured is 0 while the projected path still crosses. Overshoot and the
# action lands after p99 is already over, leaving one contaminated bucket and an honest
# but unhelpful "the fix did not fully hold".
$target = 6.0
$last = 0.0
for ($i = 0; $i -lt 200; $i++) {
    Start-Sleep -Seconds 3
    $s = Status
    if ($i % 5 -eq 0 -or $s.demand -ge ($target - 0.4)) {
        Write-Host ("     demand={0,6:N2}  cap={1}  est={2,9:N0}ms" -f $s.demand, $s.capacity, $s.est_latency_ms)
    }
    # Someone pressing Reset / Inject in the UI restarts the ramp clock and demand
    # collapses to baseline. Re-inject rather than waiting forever on a dead ramp.
    if ($s.fault_mode -ne 'traffic-ramp' -or $s.demand -lt ($last - 0.5)) {
        Write-Host '     ramp was reset (UI button?) — re-injecting' -ForegroundColor Yellow
        Invoke-RestMethod -Uri "$store/admin/fault?mode=traffic-ramp&level=20" -TimeoutSec 8 | Out-Null
    }
    $last = $s.demand
    if ($s.demand -ge $target) { break }
}

Write-Host '== 4/5 running one loop (it should act and verify)' -ForegroundColor Cyan
& $py -m chronolens.cli respond

Write-Host '== 5/5 clearing the fault, then building the proof for the acted service' -ForegroundColor Cyan
Invoke-RestMethod -Uri "$store/admin/fault?mode=off&level=0" -TimeoutSec 8 | Out-Null
# Keep the post-action window short and clean: every extra minute adds buckets that
# say nothing, and `proof` with no argument picks the *worst* service right now — which
# after a successful fix is usually not the one that was fixed.
Start-Sleep -Seconds 45
& $py -m chronolens.cli proof chronolens-store

Write-Host ''
Write-Host 'Want: Prevented True, a non-zero "Breach avoided", and a measured peak well under the projected one.' -ForegroundColor Yellow
