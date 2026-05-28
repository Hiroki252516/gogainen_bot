from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./.local/app.db"
    ai_backend: str = "mock"
    codex_app_server_url: str = "ws://host.docker.internal:4500"
    codex_ws_token_file: str | None = None
    codex_model: str | None = None
    max_learning_targets: int = 4
    max_turns_per_term: int = 3
    random_seed: str = "20260525"
    export_dir: str = "./exports"
    frontend_origin: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def ensure_dirs(self) -> None:
        Path(self.export_dir).mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite:///"):
            db_path = self.database_url.removeprefix("sqlite:///")
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
