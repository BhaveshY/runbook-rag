import asyncio
import json
import math
import random

import httpx

from .config import Settings

ATTEMPTS = 3
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
QUOTA_EXHAUSTED = {"insufficient_quota", "billing_hard_limit_reached"}


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
        for attempt in range(ATTEMPTS):
            final = attempt == ATTEMPTS - 1
            try:
                response = await self.http.post(path, json=payload)
            except httpx.RequestError:
                if final:
                    raise ProviderError(
                        "The model provider is unavailable. Please try again."
                    ) from None
            else:
                if response.is_success:
                    return json_object(response)
                raise_unless_retryable(response, final)
            await asyncio.sleep(0.5 * (2**attempt) + random.random() * 0.15)
        raise AssertionError("unreachable")

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
            vectors = checked_vectors(result, len(texts), self.settings.dimensions)
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ProviderError(
                "The embedding provider returned invalid vectors. Please retry."
            ) from None
        return vectors, token_usage(result, "total_tokens")

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
        model = model or self.settings.model
        result = await self.post(
            "/responses",
            {
                "model": model,
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
        except (ValueError, TypeError, AttributeError):
            raise ProviderError(
                "The model returned an unreadable response. Please retry."
            ) from None
        return answer, {
            "input_tokens": token_usage(result, "input_tokens"),
            "output_tokens": token_usage(result, "output_tokens"),
            "model": result.get("model") or model,
        }


def json_object(response: httpx.Response) -> dict:
    try:
        result = response.json()
    except ValueError:
        raise ProviderError(
            "The model provider returned an unreadable response. Please retry."
        ) from None
    if not isinstance(result, dict):
        raise ProviderError("The model provider returned an invalid response format.")
    return result


def raise_unless_retryable(response: httpx.Response, final: bool) -> None:
    status = response.status_code
    if status in (401, 403):
        raise ProviderError("The model provider rejected this server's credentials.")
    if status == 429 and error_code(response) in QUOTA_EXHAUSTED:
        raise ProviderError("The model provider's account has no available quota.")
    if status not in RETRYABLE_STATUS or final:
        raise ProviderError(
            f"The model provider could not complete this request (HTTP {status})."
        )


def error_code(response: httpx.Response) -> str | None:
    try:
        return response.json().get("error", {}).get("code")
    except (ValueError, AttributeError):
        return None


def checked_vectors(result: dict, count: int, dimensions: int) -> list[list[float]]:
    rows = sorted(result["data"], key=lambda row: row["index"])
    if len(rows) != count or any(
        type(row["index"]) is not int or row["index"] != i for i, row in enumerate(rows)
    ):
        raise ValueError("Embedding rows do not match the inputs.")
    for row in rows:
        vector = row["embedding"]
        if not isinstance(vector, list) or len(vector) != dimensions:
            raise ValueError("Wrong embedding dimensions.")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in vector):
            raise ValueError("Non-finite embedding value.")
        if not 1e-24 < sum(v * v for v in vector) < 1e30:
            raise ValueError("Degenerate embedding norm.")
    return [row["embedding"] for row in rows]


def token_usage(result: dict, key: str) -> int:
    usage = result.get("usage")
    value = usage.get(key, 0) if isinstance(usage, dict) else 0
    return value if type(value) is int and value >= 0 else 0
