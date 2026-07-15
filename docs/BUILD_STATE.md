# Build State
current_phase: 1
status: in_progress
completed_phases: [0]
decisions_log:
  - 2026-07-15: Phase 0 started on an empty directory; no prior repo state to resume from.
  - 2026-07-15: Pinned Next.js to 15 via create-next-app@15 — `@latest` now installs Next 16, outside the settled stack decision (Appendix B.8).
  - 2026-07-15: Added pydantic-settings beyond the listed API deps for typed config at the boundary; secrets remain env-only.
  - 2026-07-15: Credentials typed `str | None` and asserted at point of use, so the API boots and /health answers without Phase 1 secrets.
  - 2026-07-15: Adopted npm workspaces (node_modules hoisted to root); Vercel will target apps/web via its root-directory setting.
  - 2026-07-15: Phase 0 verified green (build, tsc, eslint, ruff, mypy strict, pytest 1/1) and accepted against live processes: /health -> 200, web renders on :3100.
blockers:
  - Phase 1 requires real Supabase credentials (SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY) on a project with PostGIS enabled. Cannot be self-generated; field persistence and RLS cannot be demonstrated without them.
