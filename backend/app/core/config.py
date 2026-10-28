from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./.local/app.db"
    ai_backend: str = "codex_app_server"
    codex_app_server_url: str = "ws://127.0.0.1:4500"
    codex_ws_token_file: str | None = None
    codex_model: str = "gpt-6-luna"
    codex_app_server_cwd: str = "/tmp"
    codex_turn_timeout_sec: int = 120
    codex_reasoning_effort: str = "low"
    rag_base_dir: str = "./rag_agent_knowledge_base"
    max_learning_targets: int = 3
    max_turns_per_term: int = 3
    export_dir: str = "./exports"
    identity_mapping_path: str = "./.private-identities/mappings.sqlite3"
    frontend_origin: str = "http://localhost:3000"
    admin_password: SecretStr = SecretStr("abc")

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
