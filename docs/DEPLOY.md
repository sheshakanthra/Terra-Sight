# Deploying TerraSight

Production reuses the existing Supabase project (migrations 0001–0004 already
applied). Web → Vercel, API → Render (Docker), daily refresh via a free GitHub
Actions schedule (Render's cron service type needs a paid plan).

Because Render and Vercel deploy from GitHub, **push the repo first.**

## Env vars

| Where | Variable | Value |
| --- | --- | --- |
| Render (API) | `WEB_ORIGIN` | the Vercel web URL, e.g. `https://terrasight.vercel.app` |
| Render (API) | `SUPABASE_URL` | `https://<ref>.supabase.co` (base, not /rest/v1/) |
| Render (API) | `SUPABASE_ANON_KEY` | Supabase → Settings → API |
| Render (API) | `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Settings → API (server-only) |
| Render (API) | `GROQ_API_KEY` | Groq console |
| Render (API) | `CRON_SECRET` | a long random string (same value in GitHub) |
| Vercel (web) | `NEXT_PUBLIC_SUPABASE_URL` | same base URL |
| Vercel (web) | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | anon key |
| Vercel (web) | `NEXT_PUBLIC_API_BASE_URL` | the Render API URL, e.g. `https://terrasight-api.onrender.com` |
| GitHub Actions | `API_BASE_URL` | the Render API URL (no trailing slash) |
| GitHub Actions | `CRON_SECRET` | same value as Render's `CRON_SECRET` |

## Order (avoids CORS/URL chicken-and-egg)

1. **Push** `main` to GitHub.
2. **Render → New → Blueprint**, select the repo. It reads `render.yaml` and
   creates the API service. Fill the `sync:false` secrets, including a long
   random `CRON_SECRET`. For `WEB_ORIGIN`, put your intended Vercel URL (see
   step 3) — you can correct it after. Deploy; note the API URL from `/health`.
3. **Vercel → Add New → Project**, import the repo. Set **Root Directory =
   `apps/web`**. Add the three `NEXT_PUBLIC_*` vars (API base = the Render URL).
   Deploy; note the web URL.
4. **Reconcile:** set Render `WEB_ORIGIN` to the actual Vercel URL; the API
   redeploys.
5. **Supabase → Authentication → URL Configuration:** set the Site URL and add
   the Vercel URL to Redirect URLs, so magic-link sign-in returns to production.
6. **GitHub Actions secrets** (Settings → Secrets and variables → Actions): add
   `API_BASE_URL` (the Render URL) and `CRON_SECRET` (matching Render's). The
   daily workflow is `.github/workflows/daily-refresh.yml`; trigger it once from
   the Actions tab ("Run workflow") to confirm it returns HTTP 200.
7. **Verify:** open the Vercel URL in a fresh browser, sign in, draw a field,
   refresh, get advice.

## Notes

- Render's free web service sleeps when idle; the first request after a sleep
  cold-starts (~50s). Fine for a demo; the daily refresh also keeps data warm.
  The GitHub Action retries on connection refusal to ride out a cold start.
- Scheduled GitHub Actions run only from the default branch and can be delayed
  under load; GitHub also disables schedules after 60 days of repo inactivity.
  Fine for a portfolio; re-enable from the Actions tab if it ever pauses.
