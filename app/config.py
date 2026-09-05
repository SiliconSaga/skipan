"""Environment-driven settings. A .env at the component root is honored for local dev."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODELS = "gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash-001"


@dataclass(frozen=True)
class Settings:
    project_id: str
    region: str
    board_sheet_id: str
    skipta_sheet_id: str
    base_url: str
    model_names: list[str] = field(default_factory=list)
    max_output_tokens: int = 1024
    rate_limit_per_minute: int = 10
    rain_threshold: int = 50
    lookback_days: int = 14

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            project_id=os.getenv("GCP_PROJECT_ID", ""),
            region=os.getenv("GCP_REGION", "us-east1"),
            board_sheet_id=os.getenv("SKIPAN_BOARD_SHEET_ID", ""),
            skipta_sheet_id=os.getenv("SKIPAN_SKIPTA_SHEET_ID", ""),
            base_url=os.getenv("SKIPAN_BASE_URL", "http://localhost:8001"),
            model_names=[m.strip() for m in os.getenv("SKIPAN_MODEL_NAMES", DEFAULT_MODELS).split(",") if m.strip()],
            max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", "1024")),
            rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")),
            rain_threshold=int(os.getenv("SKIPAN_RAIN_THRESHOLD", "50")),
            lookback_days=int(os.getenv("SKIPAN_LOOKBACK_DAYS", "14")),
        )
