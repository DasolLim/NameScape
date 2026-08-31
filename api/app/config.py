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
    #: DEVELOPMENT ONLY. Skips the Claude classifier so a machine with no API
    #: key can still submit. Must never be true in production: it turns the
    #: fail-closed pipeline into a fail-open one.
    moderation_dev_bypass: bool = False
    sentry_dsn: str = ""
    #: Writes allowed per address per minute. Raised for contract fuzzing,
    #: where the limiter would otherwise answer before request validation.
    writes_per_minute: int = 30
    #: Only enable behind a proxy you control: a client can otherwise forge
    #: X-Forwarded-For and get a fresh allowance per request.
    trust_forwarded_for: bool = False
    #: OpenRouter, for offline work only: etymology resolution and puzzle clue
    #: drafting. With no key the model tier is skipped, which is a supported
    #: state - the tiers above it are the citable ones.
    openrouter_api_key: str = ""
    #: Confirm the slug against OpenRouter's model list before relying on it.
    #: Quality matters more than cost here: a few hundred calls a year.
    openrouter_model: str = "anthropic/claude-opus-5"

    #: Claims allowed per address per day without an account. Low on purpose:
    #: a guest claim locks a place for a week and costs nothing to make.
    guest_claims_per_day: int = 3

    #: Where the sign-in link should send people back to.
    app_base_url: str = "http://localhost:5173"
    #: Mail. With no host configured the link is logged instead of sent, which
    #: is what development wants and production must never rely on.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "Toponomicon <no-reply@toponomicon.example>"
    smtp_start_tls: bool = True


settings = Settings()
