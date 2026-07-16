-- TerraSight — Phase 1: fields
--
-- Apply via the Supabase SQL editor (Dashboard -> SQL Editor -> New query),
-- or with psql against the project's connection string. Idempotent: safe to
-- re-run.

create extension if not exists postgis;

create table if not exists public.fields (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid not null references auth.users (id) on delete cascade,
    name       text not null,
    geom       geometry(Polygon, 4326) not null,
    area_ha    double precision not null,
    created_at timestamptz not null default now(),

    constraint fields_name_length check (char_length(btrim(name)) between 1 and 80),
    -- Mirrors the API's server-side limits so a direct PostgREST call cannot
    -- bypass them. Kept deliberately loose at the edges; the API owns the
    -- friendly messaging.
    constraint fields_area_bounds check (area_ha >= 0.5 and area_ha <= 500),
    constraint fields_geom_valid check (st_isvalid(geom))
);

create index if not exists fields_user_id_idx on public.fields (user_id);
create index if not exists fields_geom_idx on public.fields using gist (geom);

-- Row Level Security -------------------------------------------------------
-- Every policy is keyed to auth.uid(). The API talks to PostgREST with the
-- caller's own JWT (never the service-role key), so these policies are the
-- real isolation boundary rather than decoration.

alter table public.fields enable row level security;

drop policy if exists fields_select_own on public.fields;
create policy fields_select_own on public.fields
    for select using (auth.uid() = user_id);

drop policy if exists fields_insert_own on public.fields;
create policy fields_insert_own on public.fields
    for insert with check (auth.uid() = user_id);

drop policy if exists fields_update_own on public.fields;
create policy fields_update_own on public.fields
    for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists fields_delete_own on public.fields;
create policy fields_delete_own on public.fields
    for delete using (auth.uid() = user_id);

-- Reads ---------------------------------------------------------------------
-- PostgREST serves geometry columns as WKB hex, which the client would have to
-- decode. This view hands back GeoJSON directly. security_invoker makes the
-- view run as the caller, so the policies above still apply through it.

create or replace view public.fields_geojson
with (security_invoker = true) as
select
    id,
    user_id,
    name,
    area_ha,
    created_at,
    st_asgeojson(geom)::jsonb as geometry
from public.fields;
