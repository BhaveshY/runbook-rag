from functools import cache

import numpy as np

from .config import Settings


@cache
def load_model(name: str, cache_dir: str):
    from fastembed import TextEmbedding

    return TextEmbedding(name, cache_dir=cache_dir)


def embed(texts: list[str], settings: Settings) -> np.ndarray:
    model = load_model(settings.embedding_model, str(settings.model_cache))
    vectors = np.asarray(list(model.embed(texts)), dtype=np.float32)
    if vectors.shape != (len(texts), settings.dimensions):
        raise ValueError(
            f"{settings.embedding_model} returned {vectors.shape[1]} dimensions, "
            f"but RUNBOOK_EMBEDDING_DIMENSIONS is {settings.dimensions}."
        )
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
