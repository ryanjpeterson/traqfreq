# traqfreq: the web app is built into the image, then served by FastAPI (uv run traqfreq) on :4492.

# ---- web: Vite build (tokens → CSS, then bundle) ----
FROM node:22-slim AS web
WORKDIR /app
COPY web/package.json web/package-lock.json web/
RUN cd web && npm ci
COPY tokens tokens
COPY scripts/build-tokens.mjs scripts/
COPY web web
RUN cd web && npm run build

# ---- app: Python 3.12 + uv ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1 PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src src
RUN uv sync --locked --no-dev
COPY --from=web /app/web/dist web/dist

# jimbo-dj's data directory is mounted read-only at /legacy (the whole folder, so SQLite sees -wal and -shm).
ENV TRAQFREQ_DATA_DIR=/data \
    TRAQFREQ_LEGACY_DB=/legacy/jimbodj.sqlite \
    TRAQFREQ_WEB_DIR=/app/web/dist \
    TRAQFREQ_HOST=0.0.0.0 \
    TRAQFREQ_PORT=4492
EXPOSE 4492
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:4492/api/health')"]
CMD ["uv", "run", "--locked", "--no-dev", "traqfreq"]
