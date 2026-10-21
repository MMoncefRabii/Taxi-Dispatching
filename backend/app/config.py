from pathlib import Path
from typing import Literal
from urllib.parse import SplitResult, unquote, urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PLACEHOLDER_DATABASE_PASSWORDS = {
    "admin",
    "changeme",
    "change_me",
    "change-me",
    "default",
    "example",
    "password",
    "password1",
    "placeholder",
    "postgres",
    "replace_with_a_long_random_password",
    "root",
    "secret",
    "123456",
    "12345678",
}


def _parse_url(value: str) -> SplitResult | None:
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError:
        return None
    return parsed


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
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
    location_max_future_seconds: float = Field(
        default=60,
        gt=0,
        allow_inf_nan=False,
        validation_alias="LOCATION_MAX_FUTURE_SECONDS",
    )
    location_max_age_live_seconds: float = Field(
        default=300,
        gt=0,
        allow_inf_nan=False,
        validation_alias="LOCATION_MAX_AGE_LIVE_SECONDS",
    )
    location_max_age_batch_seconds: float = Field(
        default=21600,
        gt=0,
        allow_inf_nan=False,
        validation_alias="LOCATION_MAX_AGE_BATCH_SECONDS",
    )
    location_min_interval_seconds: float = Field(
        default=2,
        gt=0,
        allow_inf_nan=False,
        validation_alias="LOCATION_MIN_INTERVAL_SECONDS",
    )
    location_max_speed_kmh: float = Field(
        default=200,
        gt=0,
        allow_inf_nan=False,
        validation_alias="LOCATION_MAX_SPEED_KMH",
    )
    location_max_accuracy_m: float = Field(
        default=50,
        gt=0,
        allow_inf_nan=False,
        validation_alias="LOCATION_MAX_ACCURACY_M",
    )
    location_batch_max: int = Field(
        default=50,
        ge=1,
        le=50,
        validation_alias="LOCATION_BATCH_MAX",
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

    def production_configuration_problems(self) -> list[str]:
        problems = []
        if "web_origins" not in self.model_fields_set:
            problems.append("WEB_ORIGINS must be explicitly set in production.")
        if "frontend_base_url" not in self.model_fields_set:
            problems.append("FRONTEND_BASE_URL must be explicitly set in production.")

        origins = self.web_origins.split(",")
        for index, raw_origin in enumerate(origins, start=1):
            origin = raw_origin.strip()
            if not origin:
                problems.append(f"WEB_ORIGINS entry {index} must not be empty.")
                continue
            if "*" in origin:
                problems.append("WEB_ORIGINS must not contain a wildcard origin.")
                continue

            parsed = _parse_url(origin)
            if parsed is None:
                problems.append(
                    f"WEB_ORIGINS entry {index} must be a bare scheme://host[:port] origin with no path."
                )
                continue
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.hostname is None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or any(character.isspace() for character in origin)
                or "?" in origin
                or "#" in origin
                or parsed.username is not None
                or parsed.password is not None
            ):
                problems.append(
                    f"WEB_ORIGINS entry {index} must be a bare scheme://host[:port] origin with no path."
                )
            if (
                parsed.scheme != "https"
                and parsed.hostname not in {"localhost", "127.0.0.1"}
            ):
                problems.append(
                    f"WEB_ORIGINS entry {index} must use HTTPS unless its host is localhost or 127.0.0.1."
                )

        base_url = _parse_url(self.frontend_base_url)
        if (
            base_url is not None
            and base_url.scheme != "https"
            and base_url.hostname not in {"localhost", "127.0.0.1"}
        ):
            problems.append(
                "FRONTEND_BASE_URL must use HTTPS unless its host is localhost or 127.0.0.1."
            )

        database_url = _parse_url(self.database_url)
        if database_url is not None and database_url.scheme.startswith("postgres"):
            password = unquote(database_url.password or "").strip().casefold()
            if password in PLACEHOLDER_DATABASE_PASSWORDS or not password:
                problems.append(
                    "DATABASE_URL password looks like a placeholder."
                )

        if self.dev_tasks_enabled:
            problems.append("DEV_TASKS_ENABLED cannot be used in production.")

        return problems

    def uses_localhost_http(self) -> bool:
        urls = [*self.web_origins.split(","), self.frontend_base_url]
        for value in urls:
            parsed = _parse_url(value.strip())
            if (
                parsed is not None
                and parsed.scheme == "http"
                and parsed.hostname in {"localhost", "127.0.0.1"}
            ):
                return True
        return False

    @property
    def async_database_url(self) -> str:
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url


settings = Settings()