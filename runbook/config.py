import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = (
    ROOT
    if (ROOT / "web/index.html").is_file()
    else Path(__file__).resolve().parent / "resources"
)
WORKSPACE = ROOT if RESOURCES == ROOT else Path.cwd()


def env(name: str, default, cast: Callable = str, secret: bool = False):
    return field(
        default_factory=lambda: cast(os.getenv(name, default)), repr=not secret
    )


@dataclass(frozen=True)
class Settings:
    data_dir: Path = env("RUNBOOK_DATA_DIR", WORKSPACE / "data", Path)
    report_path: Path = env(
        "RUNBOOK_EVAL_REPORT", WORKSPACE / "eval/results/latest.json", Path
    )
    model_cache: Path = env("RUNBOOK_MODEL_CACHE", WORKSPACE / "data/models", Path)
    backend: str = env("RUNBOOK_BACKEND", "codex")
    api_key: str = env("OPENAI_API_KEY", "", secret=True)
    base_url: str = env(
        "OPENAI_BASE_URL", "https://api.openai.com/v1", lambda url: url.rstrip("/")
    )
    model: str = env("RUNBOOK_MODEL", "gpt-5.6-luna")
    rerank_model: str = env("RUNBOOK_RERANK_MODEL", "gpt-5.6-luna")
    review_model: str = env("RUNBOOK_REVIEW_MODEL", "gpt-5.6-luna")
    judge_model: str = env("RUNBOOK_JUDGE_MODEL", "gpt-5.6-sol")
    judge_reasoning: str = env("RUNBOOK_JUDGE_REASONING", "low")
    embedding_model: str = env("RUNBOOK_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    dimensions: int = env("RUNBOOK_EMBEDDING_DIMENSIONS", "384", int)
    access_token: str = env("RUNBOOK_ACCESS_TOKEN", "", secret=True)
    daily_limit: int = env("RUNBOOK_DAILY_REQUEST_LIMIT", "200", int)
