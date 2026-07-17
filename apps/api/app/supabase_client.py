"""Supabase client construction.

Requests are made with the caller's own JWT, so PostgREST applies the RLS
policies on public.fields. The service-role key bypasses RLS entirely and is
therefore reserved for unattended jobs (the Phase 7 cron), never for handling a
user request.
"""

from supabase import AsyncClient, create_async_client
from supabase.lib.client_options import AsyncClientOptions

from app.config import get_settings


class SupabaseNotConfiguredError(RuntimeError):
    """Supabase credentials are absent from the environment."""


def _require_project_config() -> tuple[str, str]:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise SupabaseNotConfiguredError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in apps/api/.env"
        )
    return settings.supabase_url, settings.supabase_anon_key


async def create_anon_client() -> AsyncClient:
    """A client holding no user session — used only to verify access tokens."""
    url, anon_key = _require_project_config()
    return await create_async_client(url, anon_key)


async def create_user_client(access_token: str) -> AsyncClient:
    """A client acting as the signed-in user, subject to RLS.

    The token is set as the Authorization header at construction so *every*
    sub-client — PostgREST and Storage alike — acts as the user. Setting it only
    on `client.postgrest` would leave Storage authenticated as anon, and the
    overlay-write RLS policy (keyed to auth.uid()) would reject the upload.
    """
    url, anon_key = _require_project_config()
    options = AsyncClientOptions(headers={"Authorization": f"Bearer {access_token}"})
    return await create_async_client(url, anon_key, options)


async def create_service_client() -> AsyncClient:
    """A service-role client that bypasses RLS — for unattended jobs only.

    Reserved for the daily cron, which must read and refresh every field across
    all users. Never use this to handle a user request; user requests act as the
    user so the RLS policies apply.
    """
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise SupabaseNotConfiguredError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in apps/api/.env"
        )
    return await create_async_client(settings.supabase_url, settings.supabase_service_role_key)
