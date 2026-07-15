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
