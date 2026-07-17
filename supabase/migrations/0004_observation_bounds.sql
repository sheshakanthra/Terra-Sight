-- TerraSight — Phase 6: persist overlay bounds
--
-- Apply after 0003_alerts.sql. Idempotent: safe to re-run.
--
-- The NDVI overlay PNG is pinned to the pixel-window extent of each date's read
-- (in EPSG:4326). That extent cannot be reproduced client-side without the
-- raster, so the dashboard's date scrubber needs it stored per observation.
-- Stored as jsonb [west, south, east, north]. Older rows stay null until their
-- next refresh; the client falls back to the field bbox for those.

alter table public.observations add column if not exists bounds jsonb;
