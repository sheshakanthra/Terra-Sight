-- TerraSight — Phase 3: alerts
--
-- Apply after 0002_observations.sql. Idempotent: safe to re-run.

-- Deterministic trend alerts. Rules (not the LLM) create these, each carrying
-- its numeric evidence. One row per (field, zone, type): a re-refresh updates
-- the row in place, so the same condition never duplicates.
create table if not exists public.alerts (
    id         uuid primary key default gen_random_uuid(),
    field_id   uuid not null references public.fields (id) on delete cascade,
    zone       text not null,            -- 'field' or a 3x3 label (NW..SE)
    type       text not null,            -- 'field_decline' | 'zone_decline'
    severity   text not null,            -- 'low' | 'medium' | 'high'
    evidence   jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint alerts_severity_valid check (severity in ('low', 'medium', 'high')),
    constraint alerts_field_zone_type_unique unique (field_id, zone, type)
);

create index if not exists alerts_field_idx on public.alerts (field_id);

-- Row Level Security ------------------------------------------------------
-- Alerts inherit their owner from the parent field, like observations.

alter table public.alerts enable row level security;

drop policy if exists alerts_select_own on public.alerts;
create policy alerts_select_own on public.alerts
    for select using (
        field_id in (select id from public.fields where user_id = auth.uid())
    );

drop policy if exists alerts_insert_own on public.alerts;
create policy alerts_insert_own on public.alerts
    for insert with check (
        field_id in (select id from public.fields where user_id = auth.uid())
    );

drop policy if exists alerts_update_own on public.alerts;
create policy alerts_update_own on public.alerts
    for update using (
        field_id in (select id from public.fields where user_id = auth.uid())
    ) with check (
        field_id in (select id from public.fields where user_id = auth.uid())
    );

drop policy if exists alerts_delete_own on public.alerts;
create policy alerts_delete_own on public.alerts
    for delete using (
        field_id in (select id from public.fields where user_id = auth.uid())
    );
