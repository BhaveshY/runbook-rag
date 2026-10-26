"""Build an immutable, checksummed corpus from a pinned upstream Git commit."""

import asyncio
import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import yaml

from .config import RESOURCES, Settings
from .provider import OpenAI
from .retrieval import Index

PIPELINE_VERSION = "heading-lines-v1"


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def clean(text: str) -> str:
    text = re.sub(
        r'\{\{[<%]\s*glossary_tooltip[^}]*text="([^"]+)"[^}]*[>%]\}\}', r"\1", text
    )
    text = re.sub(r"\{\{[<%].*?[>%]\}\}", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^\n)]+\)", r"\1", text)
    return text.strip()


def chunk_document(doc: dict, raw: str, manifest: dict) -> list[dict]:
    lines = raw.splitlines()
    start = 0
    title = doc["id"]
    if lines and lines[0] == "---":
        end = lines.index("---", 1)
        title = str(yaml.safe_load("\n".join(lines[1:end])).get("title", title))
        start = end + 1
    sections, headings, section_start, in_code = [], [], start, False
    for i in range(start, len(lines)):
        if lines[i].lstrip().startswith("```"):
            in_code = not in_code
        heading = re.match(r"^(#{2,6})\s+(.+)", lines[i]) if not in_code else None
        if heading:
            if i > section_start:
                sections.append(
                    (section_start, i, " / ".join(h[1] for h in headings) or "Overview")
                )
            level = len(heading[1])
            headings = [h for h in headings if h[0] < level]
            headings.append((level, re.sub(r"\s*\{#.*\}\s*", "", heading[2]).strip()))
            section_start = i
    sections.append(
        (section_start, len(lines), " / ".join(h[1] for h in headings) or "Overview")
    )
    chunks = []
    for lo, hi, heading in sections:
        cursor = lo
        while cursor < hi:
            end, size, fence = cursor, 0, False
            while end < hi:
                line = lines[end]
                size += len(line) + 1
                if line.lstrip().startswith("```"):
                    fence = not fence
                end += 1
                if size >= 1500 and not fence and (not line.strip() or size >= 2400):
                    break
            text = clean("\n".join(lines[cursor:end]))
            if len(text) >= 100:
                identity = f"{doc['id']}:{cursor}:{end}:{text}"
                chunks.append(
                    {
                        "id": f"{doc['id']}:{digest(identity.encode())[:12]}",
                        "document_id": doc["id"],
                        "title": title,
                        "heading": heading,
                        "text": text,
                        "line_start": cursor + 1,
                        "line_end": end,
                        "source_url": f"https://github.com/{manifest['repository']}/blob/{manifest['revision']}/{doc['path']}#L{cursor + 1}-L{end}",
                        "docs_url": f"https://v{manifest['version'].replace('.', '-')}.docs.kubernetes.io/"
                        + doc["path"].removeprefix("content/en/").removesuffix(".md")
                        + "/",
                        "version": manifest["version"],
                        "source_sha256": digest(raw.encode()),
                    }
                )
            cursor = end
    return chunks


async def ingest(settings: Settings) -> dict:
    settings.data_dir.mkdir(exist_ok=True, parents=True)
    with (settings.data_dir / ".ingest.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("An ingestion is already running.") from None
        return await _ingest(settings)


async def _ingest(settings: Settings) -> dict:
    source_path = settings.data_dir / "sources.json"
    manifest = json.loads(
        (
            source_path if source_path.exists() else RESOURCES / "data/sources.json"
        ).read_text()
    )
    if not re.fullmatch(r"[a-f0-9]{40}", manifest["revision"]):
        raise ValueError("Pin a full upstream commit SHA before ingestion.")
    raw_dir = settings.data_dir / "raw" / manifest["revision"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(6)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:

        async def fetch(doc):
            path = raw_dir / f"{doc['id']}.md"
            if path.exists():
                raw = path.read_text()
            else:
                async with semaphore:
                    response = await http.get(
                        f"https://raw.githubusercontent.com/{manifest['repository']}/{manifest['revision']}/{doc['path']}"
                    )
                    response.raise_for_status()
                    raw = response.text
                    temporary = path.with_suffix(".tmp")
                    temporary.write_text(raw)
                    temporary.replace(path)
            return chunk_document(doc, raw, manifest)

        groups = await asyncio.gather(*(fetch(doc) for doc in manifest["documents"]))
    chunks = [chunk for group in groups for chunk in group]
    if not chunks or any(not group for group in groups):
        raise ValueError("Every source must yield at least one chunk.")
    serialized = json.dumps(chunks, ensure_ascii=False, sort_keys=True).encode()
    configuration = json.dumps(
        {
            "pipeline": PIPELINE_VERSION,
            "model": settings.embedding_model,
            "dimensions": settings.dimensions,
        },
        sort_keys=True,
    ).encode()
    corpus_id = digest(serialized + configuration)[:20]
    index_root = settings.data_dir / "index"
    index_root.mkdir(exist_ok=True)
    target = index_root / corpus_id
    if target.is_dir():
        # Never republish a damaged cached generation as a successful ingestion.
        metadata = Index(settings, corpus_id).manifest
        print(f"Reusing {corpus_id}: {len(chunks)} chunks", flush=True)
    else:
        print(
            f"Embedding {len(chunks)} chunks from {len(groups)} pinned documents",
            flush=True,
        )
        client = OpenAI(settings)
        gate = asyncio.Semaphore(3)

        async def embed_batch(batch):
            async with gate:
                return await client.embed(
                    [f"{c['title']} > {c['heading']}\n\n{c['text']}" for c in batch]
                )

        try:
            results = await asyncio.gather(
                *(embed_batch(chunks[i : i + 48]) for i in range(0, len(chunks), 48))
            )
        finally:
            await client.close()
        vectors = np.asarray([v for rows, _ in results for v in rows], dtype=np.float32)
        if not np.isfinite(vectors).all():
            raise ValueError("Non-finite embedding returned.")
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        staging = Path(tempfile.mkdtemp(prefix=".build-", dir=settings.data_dir))
        try:
            (staging / "chunks.json").write_bytes(serialized)
            np.save(staging / "vectors.npy", vectors, allow_pickle=False)
            metadata = {
                "corpus_id": corpus_id,
                "built_at": datetime.now(UTC).isoformat(),
                "version": manifest["version"],
                "revision": manifest["revision"],
                "license": manifest["license"],
                "documents": len(groups),
                "chunks": len(chunks),
                "pipeline": PIPELINE_VERSION,
                "embedding_model": settings.embedding_model,
                "dimensions": settings.dimensions,
                "embedding_tokens": sum(tokens for _, tokens in results),
                "chunks_sha256": digest(serialized),
                "vectors_sha256": digest((staging / "vectors.npy").read_bytes()),
                "sources": [
                    {
                        "id": doc["id"],
                        "title": group[0]["title"],
                        "chunks": len(group),
                        "sha256": group[0]["source_sha256"],
                        "path": doc["path"],
                    }
                    for doc, group in zip(manifest["documents"], groups, strict=True)
                ],
            }
            (staging / "manifest.json").write_text(
                json.dumps(metadata, indent=2) + "\n"
            )
            os.replace(staging, target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    pointer = index_root / "current.tmp"
    pointer.write_text(json.dumps({"corpus_id": corpus_id}))
    os.replace(pointer, index_root / "current.json")
    return metadata
