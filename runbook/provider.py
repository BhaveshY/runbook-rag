import asyncio
import json
import math
import random

import httpx

from .config import Settings


class ProviderError(Exception):
    """An upstream failure safe to show to a client; never includes request headers."""


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
            raise ProviderError(
                "OpenAI is not configured. Ask the operator to set OPENAI_API_KEY."
            )
        for attempt in range(3):
            try:
                response = await self.http.post(path, json=payload)
            except httpx.RequestError:
                if attempt == 2:
                    raise ProviderError(
                        "The model provider is unavailable. Please try again."
                    ) from None
            else:
                if response.is_success:
                    try:
                        result = response.json()
                    except ValueError:
                        raise ProviderError(
                            "The model provider returned an unreadable response. Please retry."
                        ) from None
                    if not isinstance(result, dict):
                        raise ProviderError(
                            "The model provider returned an invalid response format."
                        )
                    return result
                if response.status_code in (401, 403):
                    raise ProviderError(
                        "The model provider rejected this server's credentials."
                    )
                if response.status_code == 429:
                    try:
                        code = response.json().get("error", {}).get("code")
                    except (ValueError, AttributeError):
                        code = None
                    if code in ("insufficient_quota", "billing_hard_limit_reached"):
                        raise ProviderError(
                            "The model provider's account has no available quota."
                        )
                if (
                    response.status_code not in (408, 429, 500, 502, 503, 504)
                    or attempt == 2
                ):
                    raise ProviderError(
                        f"The model provider could not complete this request (HTTP {response.status_code})."
                    )
            await asyncio.sleep(0.5 * (2**attempt) + random.random() * 0.15)
        raise ProviderError("The model provider is unavailable.")

    async def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        result = await self.post(
            "/embeddings",
            {
                "model": self.settings.embedding_model,
                "input": texts,
                "dimensions": self.settings.dimensions,
                "encoding_format": "float",
            },
        )
        try:
            rows = sorted(result["data"], key=lambda row: row["index"])
            if len(rows) != len(texts) or any(
                type(row["index"]) is not int or row["index"] != i
                for i, row in enumerate(rows)
            ):
                raise ValueError()
            for row in rows:
                vector = row["embedding"]
                if (
                    not isinstance(vector, list)
                    or len(vector) != self.settings.dimensions
                ):
                    raise ValueError()
                if any(
                    type(v) not in (int, float) or not math.isfinite(v) for v in vector
                ):
                    raise ValueError()
                norm_squared = sum(v * v for v in vector)
                if not 1e-24 < norm_squared < 1e30:
                    raise ValueError()
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ProviderError(
                "The embedding provider returned invalid vectors. Please retry."
            ) from None
        return [row["embedding"] for row in rows], token_usage(result, "total_tokens")

    async def structured(
        self,
        system: str,
        content: str,
        schema: dict,
        name: str,
        max_tokens: int = 2200,
        model: str | None = None,
        reasoning_effort: str = "none",
    ) -> tuple[dict, dict]:
        result = await self.post(
            "/responses",
            {
                "model": model or self.settings.model,
                "store": False,
                "reasoning": {"effort": reasoning_effort},
                "input": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": name,
                        "strict": True,
                        "schema": schema,
                    }
                },
                "max_output_tokens": max_tokens,
            },
        )
        if result.get("status") != "completed":
            raise ProviderError(
                "The model did not finish a complete answer. Please retry with a shorter incident."
            )
        try:
            text = "".join(
                part.get("text", "")
                for item in result.get("output", [])
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            answer = json.loads(text)
            if not isinstance(answer, dict):
                raise ValueError()
            return answer, {
                "input_tokens": token_usage(result, "input_tokens"),
                "output_tokens": token_usage(result, "output_tokens"),
                "model": result.get("model") or model or self.settings.model,
            }
        except (ValueError, TypeError, AttributeError):
            raise ProviderError(
                "The model returned an unreadable response. Please retry."
            ) from None


def token_usage(result: dict, key: str) -> int:
    usage = result.get("usage")
    value = usage.get(key, 0) if isinstance(usage, dict) else 0
    return value if type(value) is int and value >= 0 else 0
