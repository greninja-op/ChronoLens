# ChronoLens — Error & Fixes Log

A running list of every problem we hit getting this running end-to-end, and the
exact fix. Read this first if something breaks on a fresh clone — most "why
won't it start" issues are already here.

---

### 1. `ModuleNotFoundError: No module named 'chronolens'`
**Cause:** the package lives under `src/`, which isn't on the path by default.
**Fix:** set `PYTHONPATH=src` before running anything.
- PowerShell: `$env:PYTHONPATH="src"`
- bash: `export PYTHONPATH=src`

### 2. SigNoz returns `401 Unauthorized`
**Cause:** wrong auth header. SigNoz expects `SIGNOZ-API-KEY` (hyphenated), **not** `Authorization`.
**Fix:** already handled in `signoz.py`. Just make sure `SIGNOZ_API_KEY` in `.env` is an **Admin/Editor** key created in SigNoz → Settings → API Keys.

### 3. `docker` not reachable / `bringup.sh` fails at preflight
**Cause:** Docker Desktop isn't running, or WSL2 integration is off.
**Fix:** start Docker Desktop, enable **WSL2 integration** for your Ubuntu distro, wait for the whale icon to go steady, then re-run `bash scripts/bringup.sh`.

### 4. `foundryctl: command not found`
**Cause:** Foundry runs on Linux/macOS; on Windows it must be used **inside WSL2**, and it must be installed there.
**Fix:** install Foundry in your WSL2 (Ubuntu) shell and run the bring-up from WSL2, not PowerShell.

### 5. Windows console crash: `UnicodeEncodeError: 'charmap' codec can't encode ...`
**Cause:** the Windows console is cp1252 and can't print some Unicode/emoji.
**Fix:** the ChronoLens CLI avoids emoji in output on purpose. If you add any, set `PYTHONIOENCODING=utf-8` before running.

### 6. OpenTelemetry warning: `Overriding of current TracerProvider is not allowed`
**Cause:** both `demo_store/store.py` and `chronolens/otel_self.py` install a TracerProvider. Harmless — it only appears if you import both in one process. In normal use they run as separate processes.
**Fix:** ignore it. (Don't import the store and the ChronoLens loop into the same Python process.)

### 7. Self-trace (`chronolens` service) doesn't show up in SigNoz
**Cause:** short-lived CLI can exit before the BatchSpanProcessor flushes its spans.
**Fix:** already handled — `loop.py` calls `otel_self.flush()` in a `finally`. If you add new short-lived entry points, call `flush()` before exit.

### 8. A SigNoz dashboard panel shows raw nanoseconds (e.g. `15000000000`)
**Cause:** a duration panel with no unit set. SigNoz renders `duration_nano` literally.
**Fix:** when creating latency panels, set the panel `yAxisUnit` to `"ns"` so SigNoz auto-scales to ms/s.

### 9. Query Builder v5 response parsing returns nothing
**Cause:** v5 response shapes vary (series/rows/aggregations nesting).
**Fix:** `signoz._first_scalar()` walks common containers defensively. If a query returns 0.0 unexpectedly, log the raw body and extend the walker.

### 10. The latency chart in Mission Control looks flat or has distorted text
**Cause (flat):** zero-based y-axis pins a healthy line to the bottom.
**Cause (text):** `preserveAspectRatio="none"` stretches the SVG non-uniformly.
**Fix:** already handled — the chart auto-zooms to the data range and matches its viewBox to the rendered pixel size (no stretch). Let it collect a few samples; inject rising load for a dramatic curve.

### 11. `port already in use`
**Cause:** a previous run of the store (:8090) or Mission Control (:8095) is still alive.
**Fix:** stop the old process (or the background terminal) before restarting.

### 12. Prediction won't "land" on camera
**Cause:** the ramp is too fast/slow for the demo.
**Fix:** tune the fault level: `POST /admin/fault?mode=traffic-ramp&level=30`. Higher level = faster ramp. Default `level=30` crosses the default capacity (~33s) and breaches the 500ms SLO (~50s) — gradual enough to forecast.
