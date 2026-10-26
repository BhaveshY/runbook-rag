import asyncio
import json
import random
import shutil
import tempfile
from pathlib import Path

import httpx

from .config import Settings

ATTEMPTS = 3
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
QUOTA_EXHAUSTED = {"insufficient_quota", "billing_hard_limit_reached"}


class ProviderError(Exception):
    pass


class OpenAI:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.http = httpx.AsyncClient(
            base_url=settings.base_url,
            headers={"Authorization": f"Bearer {settings.api_key}"},
            timeout=httpx.Timeout(45, connect=8),
            limits=httpx.Limits(max_connections=12, max_keepalive_connections=8),
        )

    @property
    def configured(self) -> bool:
        return bool(self.settings.api_key)

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


class Codex:
    """Runs model calls through `codex exec`, billed to the signed-in ChatGPT plan."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return shutil.which("codex") is not None

    async def close(self):
        pass

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
        with tempfile.TemporaryDirectory(prefix="runbook-codex-") as workdir:
            schema_path = Path(workdir, f"{name}.json")
            schema_path.write_text(json.dumps(schema))
            try:
                process = await asyncio.create_subprocess_exec(
                    "codex",
                    "exec",
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--sandbox",
                    "read-only",
                    "--cd",
                    workdir,
                    "--model",
                    model,
                    "--config",
                    f"model_reasoning_effort={reasoning_effort}",
                    "--output-schema",
                    str(schema_path),
                    "--json",
                    "-",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            except FileNotFoundError:
                raise ProviderError(
                    "Codex CLI is not installed. Install it and run `codex login`."
                ) from None
            try:
                stdout, _ = await process.communicate(f"{system}\n\n{content}".encode())
            except BaseException:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                raise
        return codex_result(stdout, model)


def codex_result(stdout: bytes, model: str) -> tuple[dict, dict]:
    events = []
    for line in stdout.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    for event in events:
        if event.get("type") == "turn.failed":
            message = json.dumps(event)
            if "model_not_found" in message:
                raise ProviderError(
                    f"Model {model} is not available to this Codex login."
                )
            raise ProviderError(
                "Codex could not complete this request. Check `codex login status` and retry."
            )
    replies = [
        event["item"].get("text", "")
        for event in events
        if event.get("type") == "item.completed"
        and event["item"].get("type") == "agent_message"
    ]
    usage = next(
        (e.get("usage", {}) for e in events if e.get("type") == "turn.completed"), {}
    )
    try:
        answer = json.loads(replies[-1])
        if not isinstance(answer, dict):
            raise ValueError()
    except (IndexError, ValueError):
        raise ProviderError(
            "The model returned an unreadable response. Please retry."
        ) from None
    return answer, {
        "input_tokens": token_usage({"usage": usage}, "input_tokens"),
        "output_tokens": token_usage({"usage": usage}, "output_tokens"),
        "model": model,
    }


def model_client(settings: Settings) -> OpenAI | Codex:
    return Codex(settings) if settings.backend == "codex" else OpenAI(settings)


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


def token_usage(result: dict, key: str) -> int:
    usage = result.get("usage")
    value = usage.get(key, 0) if isinstance(usage, dict) else 0
    return value if type(value) is int and value >= 0 else 0
