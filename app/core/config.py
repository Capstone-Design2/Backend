# app/core/config.py
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):

    DEPLOY_PHASE: str = "local"
    SKIP_AUTH: bool = False
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    MST_DIR: Path = BASE_DIR / "mnt" / "data"


settings = Settings()
