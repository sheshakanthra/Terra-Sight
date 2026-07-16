-- TerraSight — Phase 2: observations + NDVI overlay storage
--
-- Apply after 0001_fields.sql. Idempotent: safe to re-run.

-- Per-field refresh cooldown is enforced against this timestamp (1 per 10 min).
alter table public.fields add column if not exists last_refreshed_at timestamptz;

-- Surface last_refreshed_at through the GeoJSON view so one read gives the
-- endpoint both the geometry and the cooldown timestamp.
--
-- CREATE OR REPLACE VIEW matches columns by position and only permits appending
-- new columns at the end, so last_refreshed_at must follow the existing columns
-- (including geometry) rather than be inserted among them. The app selects by
-- name, so column order is irrelevant to it.
create or replace view public.fields_geojson
with (security_invoker = true) as
select
    id,
    user_id,
    name,
    area_ha,
    created_at,
    st_asgeojson(geom)::jsonb as geometry,
    last_refreshed_at
from public.fields;

-- Per-date NDVI statistics for a field. Rasters are never stored here; only the
-- summary stats and the 3x3 zonal grid. One PNG overlay per date lives in
-- Supabase Storage (bucket below); raw imagery stays on AWS.
create table if not exists public.observations (
    id         uuid primary key default gen_random_uuid(),
    field_id   uuid not null references public.fields (id) on delete cascade,
    date       date not null,
    scene_id   text not null,
    stats      jsonb not null,
    zonal      jsonb not null,
    valid_pct  double precision not null,
    overlay_path text,
    created_at timestamptz not null default now(),

    constraint observations_valid_pct_range check (valid_pct >= 0 and valid_pct <= 100),
    -- At most one observation per field per calendar date; a re-refresh updates
    -- it in place rather than duplicating.
    constraint observations_field_date_unique unique (field_id, date)
);

create index if not exists observations_field_date_idx
    on public.observations (field_id, date desc);

-- Row Level Security ------------------------------------------------------
-- Observations inherit their owner from the parent field. Every policy checks
-- that the field belongs to the caller, so the same JWT that guards fields
-- guards their observations.

alter table public.observations enable row level security;

drop policy if exists observations_select_own on public.observations;
create policy observations_select_own on public.observations
    for select using (
        field_id in (select id from public.fields where user_id = auth.uid())
    );

drop policy if exists observations_insert_own on public.observations;
create policy observations_insert_own on public.observations
    for insert with check (
        field_id in (select id from public.fields where user_id = auth.uid())
    );

drop policy if exists observations_update_own on public.observations;
create policy observations_update_own on public.observations
    for update using (
        field_id in (select id from public.fields where user_id = auth.uid())
    ) with check (
        field_id in (select id from public.fields where user_id = auth.uid())
    );

-- NDVI overlay storage ----------------------------------------------------
-- Public-read bucket: overlays are derived colour PNGs, not raw imagery, and
-- the map pins them by bounds held in our DB. Objects are keyed
-- <field_id>/<date>.png so ownership can be enforced from the path.

insert into storage.buckets (id, name, public)
values ('ndvi-overlays', 'ndvi-overlays', true)
on conflict (id) do nothing;

drop policy if exists overlays_read on storage.objects;
create policy overlays_read on storage.objects
    for select using (bucket_id = 'ndvi-overlays');

drop policy if exists overlays_write_own on storage.objects;
create policy overlays_write_own on storage.objects
    for insert with check (
        bucket_id = 'ndvi-overlays'
        and (storage.foldername(name))[1]::uuid in (
            select id from public.fields where user_id = auth.uid()
        )
    );

drop policy if exists overlays_update_own on storage.objects;
create policy overlays_update_own on storage.objects
    for update using (
        bucket_id = 'ndvi-overlays'
        and (storage.foldername(name))[1]::uuid in (
            select id from public.fields where user_id = auth.uid()
        )
    );
