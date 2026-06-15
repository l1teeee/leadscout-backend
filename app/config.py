from pathlib import Path

from pydantic import SecretStr, model_validator
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

    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: SecretStr = SecretStr("")

    GOOGLE_PLACES_API_KEY: str = ""
    PAGESPEED_API_KEY: str = ""

    REDIS_URL: str = ""

    SIGNING_SECRET: SecretStr = SecretStr("")

    OPENAI_API_KEY: SecretStr = SecretStr("")
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_ANALYSIS_MODEL: str = "gpt-4o"

    BREVO_API_KEY: SecretStr = SecretStr("")
    BREVO_SENDER_EMAIL: str = "notifications@scoutia.dev"
    BREVO_SENDER_NAME: str = "Scoutia"

    LOG_LEVEL: str = "info"

    PROXY_LIST: str = ""
    PLAYWRIGHT_ENABLED: bool = False
    SCRAPER_MAX_CONCURRENCY: int = 8
    SCRAPER_BROWSER_CONCURRENCY: int = 2
    SCRAPER_PER_DOMAIN_RPS: float = 0.5
    SCRAPER_MAX_RETRIES: int = 2
    SCRAPER_CB_FAILURE_THRESHOLD: int = 4
    SCRAPER_CB_COOLDOWN_S: int = 300

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        if self.APP_ENV == "production":
            missing = []
            if not self.SUPABASE_SERVICE_ROLE_KEY.get_secret_value():
                missing.append("SUPABASE_SERVICE_ROLE_KEY")
            if not self.OPENAI_API_KEY.get_secret_value():
                missing.append("OPENAI_API_KEY")
            if not self.SIGNING_SECRET.get_secret_value():
                missing.append("SIGNING_SECRET")
            if missing:
                raise ValueError(f"Required secrets missing in production: {', '.join(missing)}")
        return self

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_origins_set(self) -> frozenset[str]:
        return frozenset(self.allowed_origins_list)

    @property
    def supabase_configured(self) -> bool:
        return bool(self.SUPABASE_URL and self.SUPABASE_SERVICE_ROLE_KEY.get_secret_value())

    @property
    def google_places_configured(self) -> bool:
        return bool(self.GOOGLE_PLACES_API_KEY)

    @property
    def openai_configured(self) -> bool:
        return bool(self.OPENAI_API_KEY.get_secret_value())

    @property
    def brevo_configured(self) -> bool:
        return bool(self.BREVO_API_KEY.get_secret_value())

    @property
    def proxies_list(self) -> list[str]:
        return [p.strip() for p in self.PROXY_LIST.split(",") if p.strip()]


settings = Settings()
