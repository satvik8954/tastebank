"""Runtime settings, read from environment / .env."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CLIENTS_DIR = DATA_DIR / "clients"

load_dotenv(ROOT / ".env")

# The fictional agency every client bank works for.
AGENCY_NAME = "Northlight Studio"


@dataclass(frozen=True)
class Settings:
    hindsight_url: str = os.getenv("HINDSIGHT_URL", "http://localhost:8888").rstrip("/")
    hindsight_api_key: str | None = os.getenv("HINDSIGHT_API_KEY") or None
    bank_prefix: str = os.getenv("BANK_PREFIX", "rz")
    groq_api_key: str | None = os.getenv("GROQ_API_KEY") or None
    llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    llm_fallback_model: str = os.getenv("LLM_FALLBACK_MODEL", "openai/gpt-oss-20b")
    vision_model: str = os.getenv("VISION_MODEL", "qwen/qwen3.8-27b")


settings = Settings()


def bank_id(client_id: str, variant: str | None = None) -> str:
    """Bank naming: `rz-crunchd`, `rz-crunchd-after`, `rz-crunchd-before`."""
    base = f"{settings.bank_prefix}-{client_id}"
    return f"{base}-{variant}" if variant else base
