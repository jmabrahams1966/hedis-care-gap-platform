from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./hedis_care_gap.db"

    jwt_secret: str = "dev-insecure-change-me"
    jwt_ttl_hours: int = 12
    magic_ttl_minutes: int = 30

    dev_mode: bool = True
    cors_origins: str = "http://localhost:5173"
    default_tenant_slug: str = "demo"

    aws_region: str = "us-east-1"
    ses_from_email: str = "no-reply@example.com"
    ses_configuration_set: str = "hedis-care-gap"
    sms_origination_number: str = "+18445550100"
    sms_configuration_set: str = "hedis-care-gap-sms"

    kms_key_arn: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
