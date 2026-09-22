from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / '.env'


class Settings(BaseSettings):
    # Resolve against the application, even when uvicorn is launched elsewhere.
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding='utf-8', extra='ignore')

    llm_provider: str = 'gemini'
    # Blank uses the selected adapter's default; explicit models survive upgrades.
    llm_model: str = ''
    gemini_api_key: SecretStr = SecretStr('')
    openai_api_key: SecretStr = SecretStr('')
    llm_timeout_seconds: float = Field(default=45, ge=1, le=180)
    llm_max_output_tokens: int = Field(default=1800, ge=256, le=8000)
    session_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    max_sessions: int = Field(default=100, ge=1, le=1000)
    max_history_turns: int = Field(default=12, ge=1, le=50)
    romaji_enabled: bool = False
    assessment_db_path: str = 'data/assessment.sqlite3'
    assessment_ttl_seconds: int = Field(default=86400, ge=60, le=604800)
