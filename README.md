# TerraSight

Satellite-derived field health and plain-language advice for smallholder farms.

Draw a field on a map. TerraSight pulls recent Sentinel-2 passes, masks out
cloud, computes NDVI over the field and a 3×3 zone grid, detects real declines
with deterministic rules, and turns them into a short, hedged action list that
always shows its evidence.

> Status: Phase 0 (scaffold). See [docs/BUILD_STATE.md](docs/BUILD_STATE.md) for
> what exists today and [docs/PROGRESS_REPORTS.md](docs/PROGRESS_REPORTS.md) for
> the phase log.

## Architecture

| Piece | Choice | Why |
| --- | --- | --- |
| `apps/web` | Next.js 15, TypeScript, Tailwind | Deploys to Vercel |
| `apps/api` | FastAPI, rasterio, shapely, pystac-client | GDAL needs a container, not a serverless function |
| Imagery | Earth Search STAC + Sentinel-2 L2A COGs on AWS | Keyless, windowed reads — no whole-scene downloads |
| Data | Supabase (Postgres + PostGIS + Auth + Storage) | Statistics live in Postgres; rasters stay on AWS |
| Inference | Groq (`llama-3.3-70b-versatile`) | Rules decide alerts, the LLM only phrases them |
| Weather | Open-Meteo | Keyless forecast + past precipitation |

## Prerequisites

- Node.js 20+
- Python 3.11
- A Supabase project with PostGIS enabled (needed from Phase 1 onward)
- A Groq API key (optional — advice falls back to templates without it)

## Running locally

```bash
git clone <repo-url> terrasight
cd terrasight
cp .env.example apps/api/.env        # fill in values
cp .env.example apps/web/.env.local  # fill in NEXT_PUBLIC_* values
```

API:

```bash
cd apps/api
python -m venv .venv
.venv/Scripts/activate        # Windows; use source .venv/bin/activate elsewhere
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

Web (from the repo root):

```bash
npm install
npm run dev
```

Web on <http://localhost:3000>, API on <http://localhost:8000>
(<http://localhost:8000/docs> for the OpenAPI browser).

## Checks

```bash
npm run typecheck && npm run lint && npm run build   # web
cd apps/api && ruff check . && mypy app && pytest     # api
```

## What TerraSight will not tell you

It is an advisory tool, not a diagnosis. It reports what the satellite can and
cannot see (including how stale the last clear pass is), hedges every cause, and
never recommends chemicals or dosages. The farmer decides.
