from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / '.env'


class Settings(BaseSettings):
    # Resolve against the application, even when uvicorn is launched elsewhere.
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding='utf-8', extra='ignore', hide_input_in_errors=True)

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
    environment: Literal['development', 'staging'] = 'development'
    frontend_url: str = ''
    database_url: SecretStr = SecretStr('')
    staging_access_enabled: bool = False
    staging_access_code: SecretStr = SecretStr('')
    staging_session_secret: SecretStr = SecretStr('')
    staging_session_hours: int = Field(default=168, ge=1, le=720)
    # Owner-controlled beta; disabled until private deployment prerequisites exist.
    account_auth_enabled: bool = False
    account_session_encryption_keys: SecretStr = SecretStr('')
    account_invited_ids: SecretStr = SecretStr('')
    # Explicit owner-only exception, default off; never expands the UUID allowlist.
    account_owner_bootstrap_ids: SecretStr = SecretStr('')
    supabase_auth_url: str = ''
    supabase_auth_publishable_key: SecretStr = SecretStr('')
    supabase_auth_timeout_seconds: float = Field(default=5, ge=1, le=10)
    ai_rate_limit_per_hour: int = Field(default=40, ge=1, le=200)
    ai_global_rate_limit_per_hour: int = Field(default=200, ge=1, le=1000)
    scope_enforcement_enabled: bool = False
    llm_failover_enabled: bool = False
    llm_fallback_provider: str = 'groq'
    groq_api_key: SecretStr = SecretStr('')
    groq_model: str = ''
    # Owner approved existing Free-plan key + ZDR for Phase 10C. Server opt-out.
    stt_enabled: bool = True
    stt_timeout_seconds: float = Field(default=30, ge=1, le=60)
    stt_rate_limit_per_hour: int = Field(default=6, ge=1, le=20)
    stt_global_rate_limit_per_hour: int = Field(default=30, ge=1, le=60)
    stt_global_rate_limit_per_day: int = Field(default=300, ge=1, le=400)
    knowledge_enabled: bool = False
    knowledge_top_k: int = Field(default=3, ge=1, le=8)
    knowledge_context_limit: int = Field(default=6000, ge=1000, le=12000)
    knowledge_min_score: float = Field(default=.35, ge=.1, le=1)
    knowledge_db_path: str = 'knowledge_base/index.sqlite3'

    @model_validator(mode='after')
    def account_auth_configuration(self):
        owner_ids = self.account_owner_bootstrap_ids.get_secret_value()
        if owner_ids:
            try:
                owners = owner_ids.split(',')
                allowed = self.account_invited_ids.get_secret_value().split(',')
                if (len(owners) != 1 or str(UUID(owners[0])) != owners[0]
                        or owners[0] not in allowed):
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError('Owner bootstrap requires one canonical UUID already in ACCOUNT_INVITED_IDS') from None
        if self.account_auth_enabled:
            from cryptography.fernet import Fernet
            try:
                keys = self.account_session_encryption_keys.get_secret_value().split(',')
                if not keys[0] or len(keys) > 3:
                    raise ValueError()
                for value in keys:
                    Fernet(value.encode('ascii'))
                ids = self.account_invited_ids.get_secret_value().split(',')
                if not ids[0] or len(ids) > 20 or any(str(UUID(value)) != value for value in ids):
                    raise ValueError()
            except (ValueError, TypeError, UnicodeError):
                raise ValueError('Account activation requires private encryption keys and invited account UUIDs') from None
            if not self.supabase_auth_url or not self.frontend_url:
                raise ValueError('Account activation requires provider and frontend origins')
            frontend = urlsplit(self.frontend_url)
            local_frontend = (self.environment == 'development' and frontend.scheme == 'http'
                              and frontend.hostname in ('localhost', '127.0.0.1', '::1'))
            if (not (frontend.scheme == 'https' or local_frontend) or not frontend.netloc
                    or frontend.username or frontend.password or frontend.path not in ('', '/')
                    or frontend.query or frontend.fragment or any(ord(c) <= 32 for c in self.frontend_url)):
                raise ValueError('Account activation requires an exact secure frontend origin')
        key = self.supabase_auth_publishable_key.get_secret_value()
        if not self.supabase_auth_url and not key:
            return self
        if any(ord(char) <= 32 for char in self.supabase_auth_url):
            raise ValueError('Use a valid Supabase Auth origin')
        try:
            origin = urlsplit(self.supabase_auth_url)
            port = origin.port
        except ValueError:
            raise ValueError('Use a valid Supabase Auth origin') from None
        hosted = (origin.scheme == 'https' and port in (None, 443)
                  and re.fullmatch(r'[a-z0-9-]+\.supabase\.co', origin.hostname or ''))
        local = (self.environment == 'development' and origin.scheme == 'http'
                 and origin.hostname in ('localhost', '127.0.0.1', '::1'))
        if (not (hosted or local) or origin.username or origin.password or origin.query
                or origin.fragment or origin.path not in ('', '/')
                or self.supabase_auth_url.strip() != self.supabase_auth_url):
            raise ValueError('Use a Supabase HTTPS project origin, or development-only HTTP loopback')
        if not re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]{10,480}', key):
            raise ValueError('Auth preparation requires a publishable key, never a privileged key')
        self.supabase_auth_url = self.supabase_auth_url.rstrip('/')
        return self

    @model_validator(mode='after')
    def staging_configuration(self):
        if self.environment == 'staging':
            origin = urlsplit(self.frontend_url)
            if origin.scheme != 'https' or not origin.netloc or origin.username or origin.password or origin.query or origin.fragment or origin.path not in ('', '/'):
                raise ValueError('Staging requires FRONTEND_URL as its HTTPS origin')
            if not self.database_url.get_secret_value().startswith(('postgresql://', 'postgres://')):
                raise ValueError('Staging requires a PostgreSQL DATABASE_URL')
            if not self.staging_access_enabled or not self.scope_enforcement_enabled:
                raise ValueError('Staging requires access and scope enforcement')
        if self.staging_access_enabled:
            if len(self.staging_access_code.get_secret_value()) < 16 or len(self.staging_session_secret.get_secret_value()) < 32:
                raise ValueError('Staging requires an access code of at least 16 characters and a signing secret of at least 32 characters')
        return self
