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
**Cause:** the Windows console is cp1252 and can't print some Unicode (the cascade/cooldown text uses `→` arrows).
**Fix:** already handled — `cli.py` calls `sys.stdout.reconfigure(encoding="utf-8")` on startup. The web UI is unaffected (JSON is UTF-8). If you write your own script that prints ChronoLens text, do the same or set `PYTHONIOENCODING=utf-8`.

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

### 13. ChronoLens acts on noise / flaps up and down
**Cause:** an over-eager forecaster reacting to a single jittery sample, or scaling repeatedly.
**Fix:** already handled by two brakes. The **confidence guard** (`foresee.confidence_guard`) needs `CHRONOLENS_MIN_SAMPLES` samples, a slope above `CHRONOLENS_MIN_SLOPE`, and a sustained rise before it acts. The **anti-flap guardrails** (`guardrails.FlapGuard`) enforce `CHRONOLENS_MIN_DWELL_S` between actions and a `CHRONOLENS_MAX_CAPACITY` ceiling. Tune these in `.env` if the demo needs to act sooner.

### 14. "ChronoLens only suggested, it didn't act"
**Cause:** the trust ladder. With `CHRONOLENS_AUTONOMY=suggest` it never acts; with `earn` it only acts after `CHRONOLENS_TRUST_MIN_SAVES` verified saves on that service.
**Fix:** set `CHRONOLENS_AUTONOMY=auto` in `.env` for the demo (the default), or run the loop enough times in `earn` mode to build a track record.

### 15. No Slack message on a prevented incident
**Cause:** no webhook configured, or the endpoint rejected the post.
**Fix:** set `CHRONOLENS_WEBHOOK_URL` to a Slack incoming webhook (or any endpoint that accepts `{"text": ...}`). If unset, NOTIFY is skipped and the loop continues — it fails open by design.

### 16. LLM explanation looks generic / no LLM called
**Cause:** `LLM_PROVIDER=none` (the default), so the rule-based explanation is used.
**Fix:** that's expected — ChronoLens runs with no API key. To enrich, set `LLM_PROVIDER=openai|bedrock|gemini` and the matching key (`OPENAI_API_KEY`, or AWS creds for Bedrock). Any failure silently falls back to the rule-based text.

### 17. Self-metrics don't appear in SigNoz
**Cause:** the OTLP metric exporter couldn't reach the collector, or `CHRONOLENS_SELF_OTEL=off`.
**Fix:** `metrics_self.py` fails open (never crashes the loop). Ensure the collector is up on `OTLP_ENDPOINT` (default `localhost:4317`) and `CHRONOLENS_SELF_OTEL` is not disabled. Metrics export on a 10s cadence and are flushed on CLI exit.

### 18. Deep-SigNoz calls (logs, silences, saved views, alert state) return nothing / 404
**Cause:** these endpoints vary across SigNoz versions (logs Query Builder, `/api/v1/silences`, `/api/v1/explorer/views`, `/api/v1/rules`). The request shapes here follow the current API but a different SigNoz build may differ.
**Fix:** by design every one of these is **fail-open** — `loop.py` wraps them in `_safe(...)` so a 404 or shape mismatch just degrades gracefully (CASCADE falls back to the static topology, CLASSIFY skips the log corroboration, the silence is simply not created, LEARN uses only the ledger). The core predict→prevent→verify→record loop never breaks. If you want these live, confirm the endpoints for your SigNoz version and adjust the builders in `signoz.py`; the logic is unit-tested with fakes in `tests/test_signoz_deep.py`.

### 19. Data-driven CASCADE shows the wrong root
**Cause:** the grouped p99-by-span query returned an unexpected shape, so the empirical root couldn't be parsed.
**Fix:** `_series_by_group()` returns `{}` on anything it can't parse, and CASCADE falls back to the static topology (`BlastPath.source == "topology"`). If you see `source == "traces"` but a wrong root, log the raw `query_range` body and extend `_series_by_group`.

### 20. `/api/v5/query_range` 400: `unknown field "queryType" in composite query`
**Cause:** current SigNoz (v5 query builder) changed the read shape — `compositeQuery` now takes only `queries` (an array of `{type:"builder_query","spec":{...}}`), **not** a `queryType` field.
**Fix (applied):** `signoz.py` builders (`build_trace_query`, `build_log_query`, `build_span_breakdown_query`) drop `queryType` from `compositeQuery`. The scalar response is `data.data.results[0].data = [[value]]`; grouped is `results[].columns` (group/aggregation) + `results[].data` rows — parsed by `_first_scalar` / `_series_by_group`. Verified live (p99 read returns correctly).

### 21. `POST /api/v2/rules` 400: `validation failed` (empty errors)
**Cause:** current SigNoz uses the **v2alpha1 / v5** alert schema. The old `condition.builderQueries` + ns threshold shape is rejected, and the error body is unhelpfully empty. Two gotchas: (a) the threshold target is in **ms** with `targetUnit:"ms"` (SigNoz converts to `duration_nano`), not raw ns; (b) **at least one notification channel is required**.
**Fix (applied):** `build_guard_alert(service, slo_ms, channels)` now emits the v2alpha1 shape — `condition.compositeQuery.queries` (v5), `thresholds.spec[{name:"critical",target:slo_ms,targetUnit:"ms",op:"above",matchType:"at_least_once",channels}]`, `evaluation` (`5m0s`/`1m0s`), `notificationSettings`, `schemaVersion:"v2alpha1"`, `version:"v5"`. The loop discovers an existing channel via `list_channels()` and routes the guard to it. Verified live — our client created a guard alert SigNoz accepted (state: firing). Dashboards (`/api/v1/dashboards`) were already accepted as-is.

### 22. After a fix, p99 stays high for a while (VERIFY looks like it failed)
**Cause:** SigNoz p99 is a **rolling-window** percentile. Right after remediation the window still holds the backlog of slow traces, so p99 only drops once they age out — a real monitoring reality, not a bug.
**Fix (applied):** the p99 read window was shortened (`service_p99_ms` default 120s → 30s) and VERIFY polls patiently (14×3s ≈ a couple of window-widths) so recovery is actually observed. Verified live: a managed run confirmed "p99 back to 44ms — breach avoided".
