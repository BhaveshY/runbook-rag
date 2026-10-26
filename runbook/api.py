import asyncio
import hashlib
import hmac
import json
import time
import uuid
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import __version__
from .answer import diagnose
from .config import RESOURCES, Settings
from .provenance import report_compatibility
from .provider import OpenAI, ProviderError
from .retrieval import Index, Retriever

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.provider = OpenAI(settings)
    app.state.retriever = None
    app.state.index_error = None
    try:
        app.state.retriever = Retriever(Index(settings), app.state.provider)
    except (OSError, ValueError, KeyError, TypeError) as error:
        app.state.index_error = (
            "Index unavailable; run python -m runbook ingest."
            if isinstance(error, FileNotFoundError)
            else "Index validation failed; rebuild the corpus."
        )
    app.state.slots = asyncio.Semaphore(4)
    app.state.rate = OrderedDict()
    app.state.budget_date = datetime.now(UTC).date()
    app.state.paid_requests = 0
    yield
    await app.state.provider.close()


app = FastAPI(
    title="Runbook",
    version=__version__,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


class BoundedBody:
    """Bound the actual received body, including requests without Content-Length."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        body = bytearray()
        try:
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > 16384:
                        return await JSONResponse(
                            {"detail": "Request is too large."}, status_code=413
                        )(scope, receive, send)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await JSONResponse(
                {"detail": "Request body timed out."}, status_code=408
            )(scope, receive, send)
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


app.add_middleware(BoundedBody)


@app.middleware("http")
async def headers(request: Request, call_next):
    if (
        request.headers.get("content-length", "").isdigit()
        and int(request.headers["content-length"]) > 16384
        and request.url.path.startswith("/api/")
    ):
        response = JSONResponse({"detail": "Request is too large."}, status_code=413)
    else:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


class Query(BaseModel):
    query: str = Field(min_length=8, max_length=4000)
    mode: Literal["bm25", "dense", "hybrid", "reranked"] = "reranked"
    k: int = Field(default=8, ge=3, le=10)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value):
        value = value.strip()
        if len(value) < 8:
            raise ValueError("Describe the incident in at least 8 characters.")
        return value


def check_access(request: Request, paid: bool):
    if settings.access_token:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            token.encode(), settings.access_token.encode()
        ):
            raise HTTPException(
                401,
                "This instance requires an access token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    now = time.monotonic()
    # Use the socket peer, never untrusted forwarding headers. Set a trusted reverse proxy explicitly when deploying.
    peer = request.client.host if request.client else "unknown"
    key = hashlib.sha256(peer.encode()).hexdigest()
    rate = request.app.state.rate
    timestamps = rate.setdefault(key, deque())
    rate.move_to_end(key)
    while timestamps and now - timestamps[0] > 60:
        timestamps.popleft()
    if len(timestamps) >= 20:
        raise HTTPException(
            429,
            "Too many requests. Wait a minute and retry.",
            headers={"Retry-After": "60"},
        )
    if paid:
        today = datetime.now(UTC).date()
        if request.app.state.budget_date != today:
            request.app.state.budget_date, request.app.state.paid_requests = today, 0
        if request.app.state.paid_requests >= settings.daily_limit:
            raise HTTPException(
                429, "This instance's daily request budget is exhausted."
            )
        request.app.state.paid_requests += 1
    timestamps.append(now)
    if len(rate) > 4096:
        rate.popitem(last=False)


def retriever_for(request: Request) -> Retriever:
    retriever = request.app.state.retriever
    if not retriever:
        raise HTTPException(503, request.app.state.index_error)
    return retriever


@app.get("/api/health")
async def health(request: Request):
    ready = request.app.state.retriever is not None
    return JSONResponse(
        {
            "status": "ready" if ready else "index_missing",
            "provider_configured": bool(settings.api_key),
            "access_required": bool(settings.access_token),
            "model": settings.model,
        },
        status_code=200 if ready else 503,
    )


@app.get("/api/corpus")
async def corpus(request: Request):
    return retriever_for(request).index.manifest


@app.get("/api/benchmark")
async def benchmark(request: Request):
    path = settings.report_path
    if not path.exists():
        return {
            "status": "not_run",
            "message": "Run python -m runbook evaluate to publish measured results.",
        }
    try:
        report = json.loads(path.read_text())
        if (
            not isinstance(report, dict)
            or report.get("status") != "completed"
            or not all(key in report for key in ("configuration", "retrieval", "cases"))
        ):
            raise ValueError()
        retriever = request.app.state.retriever
        report["compatibility"] = report_compatibility(
            report,
            settings,
            retriever.index.manifest["corpus_id"] if retriever else None,
        )
        return report
    except (OSError, ValueError, TypeError, AttributeError):
        raise HTTPException(
            503,
            "The evaluation report is unreadable. Ask the operator to rerun the evaluation.",
        ) from None


@app.post("/api/search")
async def search(body: Query, request: Request):
    retriever = retriever_for(request)
    check_access(request, paid=body.mode != "bm25")
    try:
        async with asyncio.timeout(55):
            async with request.app.state.slots:
                sources, trace = await retriever.search(body.query, body.mode, body.k)
        return {
            "sources": sources,
            "trace": trace,
            "corpus_id": retriever.index.manifest["corpus_id"],
        }
    except (ProviderError, TimeoutError) as error:
        raise HTTPException(
            503, str(error) or "Retrieval timed out. Please retry."
        ) from None


@app.post("/api/diagnose")
async def diagnosis(body: Query, request: Request):
    retriever = retriever_for(request)
    check_access(request, paid=True)
    try:
        async with asyncio.timeout(65):
            async with request.app.state.slots:
                return await diagnose(retriever, body.query, body.mode, body.k)
    except (ProviderError, TimeoutError) as error:
        raise HTTPException(
            503, str(error) or "The diagnosis timed out. Please retry."
        ) from None


def event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/diagnose/stream")
async def stream(body: Query, request: Request):
    retriever = retriever_for(request)
    check_access(request, paid=True)

    async def generate():
        started = time.perf_counter()
        request_id = uuid.uuid4().hex[:12]
        yield event("status", {"stage": "retrieving", "request_id": request_id})
        try:
            async with asyncio.timeout(65):
                async with request.app.state.slots:
                    sources, trace = await retriever.search(
                        body.query, body.mode, body.k
                    )
                    yield event("evidence", {"sources": sources, "trace": trace})
                    if await request.is_disconnected():
                        return
                    yield event("status", {"stage": "generating"})
                    result = await diagnose(
                        retriever, body.query, body.mode, body.k, sources, trace
                    )
                    result["trace"]["total_ms"] = round(
                        (time.perf_counter() - started) * 1000, 2
                    )
                    result["request_id"] = request_id
                    yield event("answer", result)
        except (ProviderError, TimeoutError) as error:
            yield event(
                "error",
                {
                    "message": str(error) or "The diagnosis timed out. Please retry.",
                    "request_id": request_id,
                },
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )


app.mount("/assets", StaticFiles(directory=RESOURCES / "web"), name="assets")


@app.get("/")
async def home():
    return FileResponse(RESOURCES / "web/index.html")


@app.get("/docs", include_in_schema=False)
async def api_docs():
    return FileResponse(RESOURCES / "web/api.html")
