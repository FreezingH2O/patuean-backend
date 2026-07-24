from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./voiceguard.db"

    jwt_secret: str = "dev-secret-change-me"
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 30

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Refresh-cookie policy. Local dev: lax + insecure. Cross-site prod (frontend and
    # API on different domains, e.g. two Vercel deployments): set COOKIE_SAMESITE=none
    # and COOKIE_SECURE=true, or the browser drops the cookie over HTTPS.
    cookie_secure: bool = False
    cookie_samesite: str = "lax"  # "lax" | "none" | "strict"

    # Anti-spoof (AWS API Gateway): POST raw audio, x-api-key header.
    antispoof_api_url: str = ""
    antispoof_api_key: str = ""

    # Typhoon ASR (OpenAI-compatible /audio/transcriptions), Bearer auth.
    asr_api_url: str = ""
    asr_api_key: str = ""
    asr_model: str = "typhoon-asr-realtime"

    # Thai LLM (OpenAI-compatible /chat/completions), Bearer auth.
    llm_api_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "typhoon-s-thaillm-8b-instruct"

    anon_live_test_limit: int = 5

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
