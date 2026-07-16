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
