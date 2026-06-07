from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    APP_NAME: str = "LeadScout AI Backend"
    APP_ENV: str = "development"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000

    # Comma-separated list of allowed browser origins.
    # Used by both CORSMiddleware and OriginGuardMiddleware.
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"

    # Enable strict origin enforcement (require Origin header, block curl/Postman).
    # Keep False in development; set True in production.
    ORIGIN_GUARD_ENABLED: bool = False

    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    GOOGLE_PLACES_API_KEY: str = ""
    PAGESPEED_API_KEY: str = ""

    REDIS_URL: str = ""

    SIGNING_SECRET: str = ""

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    LOG_LEVEL: str = "info"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_origins_set(self) -> frozenset[str]:
        return frozenset(self.allowed_origins_list)

    @property
    def supabase_configured(self) -> bool:
        return bool(self.SUPABASE_URL and self.SUPABASE_SERVICE_ROLE_KEY)

    @property
    def google_places_configured(self) -> bool:
        return bool(self.GOOGLE_PLACES_API_KEY)

    @property
    def openai_configured(self) -> bool:
        return bool(self.OPENAI_API_KEY)


settings = Settings()
