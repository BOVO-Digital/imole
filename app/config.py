from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    imole_base_url: str = "https://api.imole.app/v1"
    imole_api_key: str = ""
    gateway_api_key: str = ""
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"
    request_timeout: float = 600.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
