from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False)
    database_url: str = Field(validation_alias="DATABASE_URL")
    app_env: Literal["development", "production"] = Field(
        default="production",
        validation_alias="APP_ENV",
    )
    dev_disable_admin_auth: bool = Field(
        default=False,
        validation_alias="DEV_DISABLE_ADMIN_AUTH",
    )

    @field_validator("app_env", mode="before")
    @classmethod
    def default_invalid_app_env(cls, value: object) -> str:
        if isinstance(value, str) and value.lower() in {"development", "production"}:
            return value.lower()
        return "production"

    @property
    def async_database_url(self) -> str:
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url


settings = Settings()