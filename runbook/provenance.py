import hashlib
from pathlib import Path

from .config import RESOURCES, Settings


def implementation_digest() -> str:
    return hashlib.sha256(
        b"".join(
            p.name.encode() + p.read_bytes()
            for p in sorted(Path(__file__).parent.glob("*.py"))
        )
    ).hexdigest()


def dataset_digest() -> str:
    return hashlib.sha256((RESOURCES / "eval/cases.json").read_bytes()).hexdigest()


def report_compatibility(
    report: dict, settings: Settings, corpus_id: str | None
) -> dict:
    differences = []
    for label, actual, expected in (
        ("corpus", corpus_id, report.get("corpus_id")),
        (
            "implementation",
            implementation_digest(),
            report.get("implementation_sha256"),
        ),
        ("dataset", dataset_digest(), report.get("dataset_sha256")),
    ):
        if actual is None or actual != expected:
            differences.append(label)
    configuration = report.get("configuration", {})
    for key in (
        "model",
        "rerank_model",
        "review_model",
        "embedding_model",
        "dimensions",
    ):
        if configuration.get(key) != getattr(settings, key):
            differences.append(key)
    return {"matches_running_instance": not differences, "differences": differences}
