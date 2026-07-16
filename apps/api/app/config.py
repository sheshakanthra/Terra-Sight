"""Typed application configuration, sourced exclusively from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api — anchor the env file here so settings do not depend on the working
# directory the process happens to be launched from.
API_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings.

    Credentials are optional at import time so the service boots (and /health
    answers) without them; each consumer asserts what it needs at point of use.
    """

    model_config = SettingsConfigDict(
        env_file=API_DIR / ".env",
        # utf-8-sig tolerates a UTF-8 BOM, which some Windows editors prepend;
        # plain utf-8 would fold the BOM into the first key and drop it silently.
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )

    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    web_origin: str = "http://localhost:3000"

    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_anon_key: str | None = None
    groq_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
