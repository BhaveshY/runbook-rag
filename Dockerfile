FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then SSL_CERT_FILE=/run/secrets/build_ca uv sync --frozen --no-dev --no-install-project; \
    else uv sync --frozen --no-dev --no-install-project; fi
COPY runbook ./runbook
COPY web ./web
COPY data ./data
COPY eval ./eval
RUN useradd --uid 10001 --create-home runbook && chown -R runbook:runbook /app
USER runbook
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]
CMD ["/app/.venv/bin/python", "-m", "runbook", "serve", "--host", "0.0.0.0", "--port", "8000"]

