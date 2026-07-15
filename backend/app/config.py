from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./hedis_care_gap.db"

    jwt_secret: str = "dev-insecure-change-me"
    jwt_ttl_hours: int = 12
    # Magic-link lifetime. Outreach links are sent by SMS/email and clicked
    # whenever the member gets to it (often hours/days later), so the default is
    # 7 days — matching the outreach retry cadence — not the 30 minutes that only
    # suits a just-requested link. Still single-use.
    magic_ttl_minutes: int = 10080

    dev_mode: bool = True
    cors_origins: str = "http://localhost:5173"
    default_tenant_slug: str = "demo"

    aws_region: str = "us-east-1"
    ses_from_email: str = "no-reply@example.com"
    ses_configuration_set: str = "hedis-care-gap"
    sms_origination_number: str = "+18445550100"
    sms_configuration_set: str = "hedis-care-gap-sms"

    kms_key_arn: str = ""
    audit_archive_bucket: str = ""  # WORM S3 bucket for the immutable audit mirror
    pii_encryption_key: str = ""  # base64 64-byte AES-256-SIV key; empty → dev fallback

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def app_base_url(self) -> str:
        """Public URL of the member/staff web app, used to build magic links.
        Derived from the first configured CORS origin (the app's own origin) so
        it stays correct per-environment without a separate setting."""
        origins = self.cors_origin_list
        return origins[0] if origins else "https://app.example.com"


settings = Settings()
