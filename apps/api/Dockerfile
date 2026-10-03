# --- Development: source bind-mounted, auto-reload, development tools installed ----------------
FROM python:3.13-slim AS dev

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    # Outside /app so the source bind mount does not hide the virtualenv.
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

EXPOSE 8000
CMD ["uvicorn", "knowvault.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "src"]

# --- Production build: runtime dependencies and the project, nothing else ----------------------
FROM python:3.13-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# --- Production: API, worker and migrations share this image -----------------------------------
FROM python:3.13-slim AS prod

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN groupadd --system --gid 10001 knowvault \
    && useradd --system --uid 10001 --gid knowvault --home-dir /app --no-create-home knowvault \
    && mkdir -p /data/uploads /data/models \
    && chown knowvault:knowvault /data/uploads /data/models

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
# Migrations run from this image too.
COPY alembic.ini ./
COPY migrations ./migrations

USER knowvault
EXPOSE 8000
# The reverse proxy's X-Forwarded-For is interpreted by the application (TRUSTED_PROXIES), so
# uvicorn's own handling is turned off.
CMD ["uvicorn", "knowvault.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-server-header"]
