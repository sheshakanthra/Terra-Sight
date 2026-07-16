from pathlib import Path

import pytest

from app.config import API_DIR, Settings


def test_env_file_is_absolute_and_anchored_to_api_dir() -> None:
    """The env file must not be a bare relative ".env".

    pydantic-settings resolves a relative env_file against the process working
    directory, which would silently load a stray repo-root .env — or nothing at
    all — depending on where uvicorn happened to be launched from.
    """
    env_file = Settings.model_config["env_file"]
    assert isinstance(env_file, Path)
    assert env_file.is_absolute()
    assert env_file == API_DIR / ".env"
    assert env_file.parent.name == "api"


def test_env_file_encoding_tolerates_a_bom() -> None:
    """Windows editors may prepend a UTF-8 BOM; plain utf-8 would fold it into
    the first key and drop that setting with no error."""
    assert Settings.model_config["env_file_encoding"] == "utf-8-sig"


def test_settings_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_ORIGIN", "https://terrasight.example")
    monkeypatch.setenv("API_PORT", "9001")

    settings = Settings()

    assert settings.web_origin == "https://terrasight.example"
    assert settings.api_port == 9001


def test_settings_load_from_a_foreign_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.app_env
    assert settings.api_port == 8000


def test_credentials_default_to_none_so_the_service_boots_without_them() -> None:
    settings = Settings()

    assert settings.supabase_url is None or isinstance(settings.supabase_url, str)
    assert settings.groq_api_key is None or isinstance(settings.groq_api_key, str)
