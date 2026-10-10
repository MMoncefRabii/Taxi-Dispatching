from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
    )
    database_url: str = Field(validation_alias="DATABASE_URL")
    web_origins: str = Field(
        default="http://localhost:5173",
        validation_alias="WEB_ORIGINS",
    )
    frontend_base_url: str = Field(
        default="http://localhost:5173",
        validation_alias="FRONTEND_BASE_URL",
    )
    dev_tasks_enabled: bool = Field(
        default=False,
        validation_alias="DEV_TASKS_ENABLED",
    )
    app_env: Literal["development", "production"] = Field(
        default="production",
        validation_alias="APP_ENV",
    )

    @field_validator("app_env", mode="before")
    @classmethod
    def default_invalid_app_env(cls, value: object) -> str:
        if isinstance(value, str) and value.lower() in {"development", "production"}:
            return value.lower()
        return "production"

    @field_validator("frontend_base_url")
    @classmethod
    def validate_frontend_base_url(cls, value: str) -> str:
        if not value or value != value.strip() or value.endswith("/"):
            raise ValueError("FRONTEND_BASE_URL must not be empty or end with a slash")
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
            parsed.port
        except ValueError as error:
            raise ValueError("FRONTEND_BASE_URL must be a valid HTTP(S) URL") from error
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("FRONTEND_BASE_URL must be a valid HTTP(S) URL")
        return value

    @property
    def allowed_web_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.web_origins.split(",")
            if origin.strip()
        ]

    @property
    def async_database_url(self) -> str:
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url


settings = Settings()