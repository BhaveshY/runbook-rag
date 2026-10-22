import asyncio
import json
import random

import httpx

from .config import Settings


class ProviderError(Exception):
    """An upstream failure safe to show to a client; never includes request headers."""

    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.status = status


class OpenAI:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.http = httpx.AsyncClient(
            base_url=settings.base_url,
            headers={"Authorization": f"Bearer {settings.api_key}"},
            timeout=httpx.Timeout(45, connect=8),
            limits=httpx.Limits(max_connections=12, max_keepalive_connections=8),
        )

    async def close(self):
        await self.http.aclose()

    async def post(self, path: str, payload: dict) -> dict:
        if not self.settings.api_key:
            raise ProviderError("OpenAI is not configured. Ask the operator to set OPENAI_API_KEY.")
        for attempt in range(3):
            try:
                response = await self.http.post(path, json=payload)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2:
                    raise ProviderError("The model provider is unavailable. Please try again.") from None
            else:
                if response.is_success:
                    return response.json()
                if response.status_code in (401, 403):
                    raise ProviderError("The model provider rejected this server's credentials.")
                if response.status_code == 429:
                    code = response.json().get("error", {}).get("code")
                    if code in ("insufficient_quota", "billing_hard_limit_reached"):
                        raise ProviderError("The model provider's account has no available quota.")
                if response.status_code not in (408, 429, 500, 502, 503, 504) or attempt == 2:
                    raise ProviderError(f"The model provider could not complete this request (HTTP {response.status_code}).")
            await asyncio.sleep(0.5 * (2 ** attempt) + random.random() * 0.15)
        raise ProviderError("The model provider is unavailable.")

    async def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        result = await self.post("/embeddings", {
            "model": self.settings.embedding_model, "input": texts,
            "dimensions": self.settings.dimensions, "encoding_format": "float",
        })
        rows = sorted(result["data"], key=lambda row: row["index"])
        if len(rows) != len(texts) or any(len(row["embedding"]) != self.settings.dimensions for row in rows):
            raise ProviderError("The embedding provider returned an incompatible vector shape.")
        return [row["embedding"] for row in rows], result.get("usage", {}).get("total_tokens", 0)

    async def structured(self, system: str, content: str, schema: dict, name: str, max_tokens: int = 2200, model: str | None = None) -> tuple[dict, dict]:
        result = await self.post("/responses", {
            "model": model or self.settings.model, "store": False,
            "reasoning": {"effort": "none"},
            "input": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            "text": {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
            "max_output_tokens": max_tokens,
        })
        if result.get("status") != "completed":
            raise ProviderError("The model did not finish a complete answer. Please retry with a shorter incident.")
        text = "".join(part.get("text", "") for item in result.get("output", []) for part in item.get("content", []) if part.get("type") == "output_text")
        try:
            return json.loads(text), {"input_tokens": result.get("usage", {}).get("input_tokens", 0), "output_tokens": result.get("usage", {}).get("output_tokens", 0), "model": result.get("model", self.settings.model)}
        except (ValueError, TypeError):
            raise ProviderError("The model returned an unreadable response. Please retry.") from None

