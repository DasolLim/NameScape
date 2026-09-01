from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable by environment or .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://toponomicon:toponomicon@localhost:55432/toponomicon"
    #: Where migrations run. Alembic needs prepared statements, which a
    #: transaction pooler does not have, so it targets a direct or session
    #: connection. Defaults to the runtime URL, which is right everywhere that
    #: is not pooled.
    database_url_direct: str = ""
    redis_url: str = "redis://localhost:56379/0"
    typesense_url: str = ""
    typesense_api_key: str = ""
    photon_url: str = ""
    wikidata_url: str = "https://www.wikidata.org"
    secret_key: str = "dev-only-change-me"
    blocklist_path: str = "data/blocklist.txt"
    #: DEVELOPMENT ONLY. Skips the Claude classifier so a machine with no API
    #: key can still submit. Must never be true in production: it turns the
    #: fail-closed pipeline into a fail-open one.
    moderation_dev_bypass: bool = False
    sentry_dsn: str = ""
    #: Writes allowed per address per minute. Raised for contract fuzzing,
    #: where the limiter would otherwise answer before request validation.
    writes_per_minute: int = 30
    #: Whether this process runs the scheduled jobs in-process. Off by
    #: default, because on serverless every function instance would start its
    #: own scheduler: there the jobs are driven by cron over HTTP instead. A
    #: long-running deployment, and `make dev`, turn it on.
    run_scheduler: bool = False
    #: Authorises the cron endpoints. They resolve contests and release claims,
    #: so an unset secret refuses everything rather than opening them.
    cron_secret: str = ""

    #: Only enable behind a proxy you control: a client can otherwise forge
    #: X-Forwarded-For and get a fresh allowance per request.
    trust_forwarded_for: bool = False
    #: OpenRouter, for offline work only: etymology resolution and puzzle clue
    #: drafting. With no key the model tier is skipped, which is a supported
    #: state - the tiers above it are the citable ones.
    openrouter_api_key: str = ""
    #: Confirm the slug against OpenRouter's model list before relying on it.
    #: Quality matters more than cost for the offline work: a few hundred calls
    #: a year, so the difference between a strong and a cheap model is pennies.
    openrouter_model: str = "openai/gpt-5-mini"
    #: Moderation runs on every caption, nickname and correction, in the
    #: request path, so it wants something fast. Not the cheapest available:
    #: this decides whether real people's text is refused.
    moderation_model: str = "openai/gpt-5-mini"

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
    smtp_from: str = "NameScape <no-reply@namescape.example>"
    smtp_start_tls: bool = True


settings = Settings()
