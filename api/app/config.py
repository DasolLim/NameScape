from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable by environment or .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://toponomicon:toponomicon@localhost:55432/toponomicon"
    redis_url: str = "redis://localhost:56379/0"
    typesense_url: str = ""
    typesense_api_key: str = ""
    photon_url: str = ""
    wikidata_url: str = "https://www.wikidata.org"
    secret_key: str = "dev-only-change-me"
    anthropic_api_key: str = ""
    blocklist_path: str = "data/blocklist.txt"


settings = Settings()
