import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("RUNBOOK_DATA_DIR", ROOT / "data")))
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""), repr=False)
    base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"))
    model: str = field(default_factory=lambda: os.getenv("RUNBOOK_MODEL", "gpt-5.4-mini"))
    rerank_model: str = field(default_factory=lambda: os.getenv("RUNBOOK_RERANK_MODEL", "gpt-5.4-nano"))
    embedding_model: str = field(default_factory=lambda: os.getenv("RUNBOOK_EMBEDDING_MODEL", "text-embedding-3-small"))
    dimensions: int = field(default_factory=lambda: int(os.getenv("RUNBOOK_EMBEDDING_DIMENSIONS", "768")))
    access_token: str = field(default_factory=lambda: os.getenv("RUNBOOK_ACCESS_TOKEN", ""), repr=False)
    daily_limit: int = field(default_factory=lambda: int(os.getenv("RUNBOOK_DAILY_REQUEST_LIMIT", "200")))
