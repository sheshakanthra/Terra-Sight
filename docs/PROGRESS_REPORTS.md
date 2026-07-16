# Progress Reports

## Phase 0 — Scaffold ✅
- Shipped: npm-workspace monorepo with `apps/web` (Next.js 15.5.20, React 19, TypeScript strict, Tailwind v4) and `apps/api` (FastAPI, Python 3.11, venv).
- Shipped: `GET /health` returning a typed `HealthResponse` (status/version/time), CORS locked to the configured web origin, app-factory structure.
- Shipped: typed settings via `pydantic-settings` — credentials read from env only, all optional at boot so the service starts without secrets.
- Shipped: lint/typecheck/test wiring — `npm run typecheck|lint|build`; ruff + mypy (strict) + pytest with config in `apps/api/pyproject.toml`.
- Shipped: `.env.example` documenting every variable, `.gitignore` excluding secrets and build output, README with clone-to-running instructions, `docs/BACKLOG.md` seeded with the deferred list.
- Key decisions:
  - Pinned Next.js to 15 (`create-next-app@15`); `@latest` installs Next 16, which is outside the settled stack decision.
  - Added `pydantic-settings` beyond the listed deps — typed config at the boundary beats `os.getenv` scattered through modules.
  - Supabase/Groq keys are `str | None` and validated at point of use, so Phase 0's health check does not depend on credentials that arrive in Phase 1.
  - npm workspaces hoist `node_modules` to the repo root; Vercel deploys `apps/web` via its root-directory setting.
- Verification: build ✅ types ✅ (tsc --noEmit, mypy strict clean over 5 files) lint ✅ (eslint, ruff) tests 1/1 ✅ runtime ✅ acceptance ✅
  - `GET /health` → `200 {"status":"ok","version":"0.1.0",...}` against a live uvicorn process.
  - `next start` → `200`, `<title>TerraSight</title>`, no create-next-app boilerplate.
- Risks / notes for next phase: Phase 1 needs real Supabase credentials (project URL, anon key, service-role key) with PostGIS enabled — persistence cannot be demonstrated without them. Note also that some unrelated process on this machine already listens on port 3000; it briefly produced a false-positive 200 during verification, so local web checks used port 3100.

## Phase 1 — Fields ✅
- Shipped: `public.fields` (id, user_id, name, geom Polygon/4326, area_ha, created_at) with PostGIS + GiST index, RLS enabled and four owner-scoped policies keyed to auth.uid(), and a `fields_geojson` view (security_invoker) that returns geometry as GeoJSON — migration in supabase/migrations/0001_fields.sql.
- Shipped: server-side geometry engine (app/geometry.py) — validates rings/closure/self-intersection/coordinate sanity and measures area in the local UTM zone; rejects <0.5 ha and >500 ha with farmer-readable messages. 32 unit tests.
- Shipped: `POST /fields` and `GET /fields` — magic-link JWT verified by Supabase Auth, requests made with the caller's own token so RLS is the real boundary; user_id taken from the token (never the body; FieldCreate is extra="forbid"). Area computed server-side. 16 API/schema tests including body-smuggling attack cases.
- Shipped: web workspace — magic-link sign-in, MapLibre satellite map with terra-draw polygon drawing, draw→name→save, and a field list that reloads from the server.
- Key decisions:
  - Fixed both env files: SUPABASE_URL / NEXT_PUBLIC_SUPABASE_URL had the /rest/v1/ endpoint suffix, which double-prefixed every query to a 404. Diagnosed against the live project (404 as-given vs 200 corrected) before changing anything.
  - API acts as the caller (anon key + user JWT), never service-role, for all request handling; service-role is reserved for the Phase 7 cron.
  - Reads via the GeoJSON view (PostgREST otherwise serves geometry as WKB hex); writes send SRID-qualified EWKT for PostGIS to cast.
  - terra-draw + official MapLibre adapter over mapbox-gl-draw (which needs patching on MapLibre). Esri World Imagery basemap — logged in BACKLOG as dev/demo-only licensing.
- Verification: build ✅ types ✅ (tsc + mypy strict, 10 files) lint ✅ (eslint + ruff) tests 48/48 ✅ runtime ✅ acceptance ✅
  - Full end-to-end vs live API + live Supabase, two real JWT users, 9/9: persist+reload demonstrated, geometry round-trips, RLS isolation proven (B cannot see A's field), too-small polygon rejected 400. Throwaway users cascade-deleted.
- Risks / notes for next phase: PostgREST schema cache lags DDL by seconds-to-minutes — expect the same after Phase 2's migrations. Esri basemap is not production-licensed. Phase 2 (imagery pipeline) is the critical path and needs no new credentials — Earth Search STAC and S3 COGs are keyless.

## Phase 2 — Imagery pipeline ✅
- Shipped: `app/imagery/` — STAC search (Earth Search, sentinel-2-l2a, bbox intersect, 45 days, cloud<60), windowed COG range-reads of red/NIR/SCL (SCL resampled 20m→10m), field rasterization, SCL cloud masking (classes 3/8/9/10/11), the 60% valid-pixel discard gate, NDVI, field stats + 3×3 zonal grid, and a brown→green PNG overlay.
- Shipped: `GET /fields/{id}/refresh` (search → analyze usable dates → upload overlay → upsert observation) and `GET /fields/{id}/observations`; per-field 1-per-10-min cooldown (429 + Retry-After).
- Shipped: migration 0002 — observations table with RLS (owner via parent field), public ndvi-overlays storage bucket with ownership-scoped write policies, fields.last_refreshed_at.
- Shipped: web — a Refresh action per field that pins the NDVI overlay to its geographic bounds on the MapLibre map, with a "N clear dates" notice.
- Key decisions:
  - Assets are keyed red/nir/scl (not B04/B08/SCL); SCL is 20m and resampled nearest onto the 10m grid before masking.
  - Tile-edge robustness: read all bands boundless (fill 0) so partial-coverage tiles don't crash on shape mismatch, and try a date's candidate scenes clearest-first until one passes the gate rather than committing to the lowest-cloud tile (which may not cover the field). Real dry-run: 3 → 6 valid dates.
  - create_user_client passes the JWT as the Authorization header so Storage (not just PostgREST) acts as the user — required for the overlay-write RLS policy.
  - Overlays pinned to the rounded pixel-window extent (not the raw bbox) so georeferencing survives window rounding.
- Verification: build ✅ types ✅ (tsc + mypy strict, 16 files) lint ✅ (eslint + ruff) tests 84/84 ✅ runtime ✅ acceptance ✅
  - Imagery core proven via a real-module dry-run (6 valid dates, NDVI 0.51-0.77). Full live end-to-end 13/13: refresh→persist→reload, overlay publicly fetchable + georeferenced, cooldown 429, RLS isolation. Throwaway users + storage objects cleaned up.
- Risks / notes for next phase: Phase 3 (trend/alert engine) is pure-function territory with mandatory unit tests and needs no new credentials or migration beyond an `alerts` table. Six valid dates over ~40 days is a healthy trend window. The two 61.2%-valid dates (tile-edge partial coverage) are legitimately included — Phase 3 rules should tolerate varying valid_pct across observations.

## Phase 3 — Trends & alert engine ✅
- Shipped: pure trend engine (app/alerts/engine.py) — linear-fit relative decline over the last 4-6 valid observations, gated by "current NDVI below the series' own median", severity tiers (low/medium/high), and distinct field_decline / zone_decline types with 3x3 zone labels (NW..SE).
- Shipped: idempotent alert persistence (app/alerts/store.py) — unique(field_id,zone,type) upsert plus clear-stale, so a refresh never duplicates and never strands a resolved alert; created_at preserved as first-seen. Evaluation runs after observations persist in the refresh flow; its failure does not fail the refresh.
- Shipped: migration 0003 (alerts + RLS), GET /fields/{id}/alerts, active_alerts on the refresh response.
- Key decisions:
  - Linear fit (not raw first-vs-last) for decline magnitude — robust to the varying valid_pct across dates.
  - "Own median" applied per series (field vs field median, zone vs zone median), so a naturally drier zone doesn't alert for being itself.
- Verification: types ✅ (mypy strict, 19 files) lint ✅ (ruff) tests 106/106 ✅ acceptance ✅
  - 17 engine unit tests (types, severities, zero-alert healthy/rising, below-median guard, insufficient data, window cap, zone localization, determinism) + 5 store idempotency tests.
  - Live integration 7/7: the real declining field produced field_decline (medium, 29.4%/38d) + 7 localized zone alerts with evidence; idempotent against the live unique constraint; RLS isolation held.
- Risks / notes for next phase: Phase 4 (weather) adds Open-Meteo (keyless) at the field centroid and escalates alert severity + tags likely_water_stress when active decline meets a dry 7-day forecast; it writes rain_next_7d_mm into alert evidence, so it will extend the alert-evaluation step (store.py) rather than the imagery pipeline. No new migration needed — evidence is jsonb. Cache weather 6h per field.
