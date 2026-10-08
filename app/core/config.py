from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Railway hands out postgresql:// URLs. SQLAlchemy would pick the older psycopg2
# driver for that scheme, so point it at psycopg 3, which this project installs.
POSTGRES_SCHEMES = ("postgresql://", "postgres://")
PSYCOPG_SCHEME = "postgresql+psycopg://"


def normalize_database_url(url: str) -> str:
    for scheme in POSTGRES_SCHEMES:
        if url.startswith(scheme):
            return PSYCOPG_SCHEME + url[len(scheme) :]
    return url


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/resume.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, value: str) -> str:
        return normalize_database_url(value)
