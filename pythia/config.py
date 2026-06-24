from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: SecretStr
    owner_telegram_id: int
    database_url: str
    openai_api_key: SecretStr
    openai_transcription_model: str
    openai_vision_model: str
    instagram_username: str | None = None
    instagram_session_file: Path | None = None
    work_dir: Path = Path("jobs")
    max_concurrent_analyses: int = 1
    frame_count: int = 8
    external_timeout_seconds: int = 120

    @field_validator("instagram_username", "instagram_session_file", mode="before")
    @classmethod
    def blank_instagram_auth_is_disabled(cls, value: object) -> object:
        """Empty environment values intentionally mean anonymous Instagram access."""
        return None if isinstance(value, str) and not value.strip() else value


settings = Settings()
