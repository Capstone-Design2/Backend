# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DEPLOY_PHASE: str = "local"
    SKIP_AUTH: bool = False

settings = Settings()
