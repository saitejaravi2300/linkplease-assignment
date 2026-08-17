import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    pseudogram_base_url: str = os.getenv("PSEUDOGRAM_BASE_URL", "https://pseudogram-api.onrender.com").rstrip("/")
    pseudogram_api_key: str = os.getenv("PSEUDOGRAM_API_KEY", "")
    database_path: str = os.getenv("DATABASE_PATH", "./data/linkplease.db")
    max_retries: int = int(os.getenv("MAX_RETRIES", "5"))
    worker_poll_seconds: float = float(os.getenv("WORKER_POLL_SECONDS", "0.25"))
    reconcile_after_seconds: float = float(os.getenv("RECONCILE_AFTER_SECONDS", "2"))
    retry_base_seconds: float = float(os.getenv("RETRY_BASE_SECONDS", "2"))
    require_webhook_signature: bool = os.getenv("REQUIRE_WEBHOOK_SIGNATURE", "true").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

settings = Settings()
