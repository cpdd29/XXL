from pathlib import Path

from app.config import BACKEND_ENV_FILE, Settings


def test_settings_load_backend_env_file_when_started_from_project_root(monkeypatch) -> None:
    project_root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(project_root)
    monkeypatch.delenv("WORKBOT_DATABASE_URL", raising=False)

    settings = Settings()

    assert BACKEND_ENV_FILE.exists()
    assert settings.database_url == "sqlite:///./workbot-dev.sqlite3"
