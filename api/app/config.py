from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable by environment or .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://toponomicon:toponomicon@localhost:55432/toponomicon"
    redis_url: str = "redis://localhost:56379/0"


settings = Settings()
