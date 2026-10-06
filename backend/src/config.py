from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Marketing Agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "*"
    trust_cf_connecting_ip: bool = False

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwks_json: str = ""
    supabase_jwt_secret: str = ""
    # Development backdoor: `dev:<role>` tokens are accepted. Refused when app_env is production.
    auth_dev_bypass: bool = False

    database_url: str = "sqlite:///./data/app.db"

    ground_truth_verified_by: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
