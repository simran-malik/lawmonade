"""All settings come from .env."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    llm_provider: str = "anthropic"   # anthropic | gemini
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    google_calendar_id: str = "primary"
    timezone: str = "America/Los_Angeles"
    ocr_min_conf: int = 80
    slack_webhook_url: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_trial_template: str = ""   # limited trial: e.g. sms_appointment_reminders
    crm_csv_url: str = ""

    # Clio (read-only)
    clio_base: str = "https://app.clio.com"
    clio_client_id: str = ""
    clio_client_secret: str = ""
    clio_redirect_uri: str = "http://127.0.0.1:8765/callback"
    clio_access_token: str = ""
    clio_refresh_token: str = ""
    clio_matter_query: str = "Sapini"

    # Our own storage, outside Clio
    db_path: Path = ROOT / "data" / "lawmonade.db"     # SQLite: shares, share_views, last_opened, audit
    snapshot_dir: Path = ROOT / "data" / "matters"     # JSON: Clio snapshots + cached digests
    share_link_secret: str = ""
    # Demo mode: the organizers' sample file (sapini-clio-data.json). Not in git.
    demo_file: Path = ROOT.parent / "Slides & Materials - Shared w- Participants" / "Sapini Case Materials" / "sapini-clio-data.json"
    share_link_days: int = 14
    firm_name: str = "Your law firm"                    # shown to providers
    public_url: str = "http://localhost:8501"           # base of share links sent to providers

    data_dir: Path = ROOT / "data"


settings = Settings()
