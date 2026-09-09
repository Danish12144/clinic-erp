# Production image for Koyeb. Alembic migrations are NOT run here — deploy
# is app-code only; run `alembic upgrade head` as a separate, explicit step
# (a Koyeb one-off "Run command" against the same DATABASE_URL_SYNC, or
# manually) before rolling out a version whose migrations haven't applied
# yet. Baking `alembic upgrade head` into the container start would let
# every replica in a multi-instance deploy race the same migration on
# every restart, which is a worse failure mode than a deploy that's
# explicitly one step (migrate, then deploy) rather than implicitly two.
FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps for psycopg2-binary's runtime (libpq) — psycopg2-binary
# vendors its own libpq so no build toolchain is needed, only the shared
# lib loader; kept minimal on purpose, not the full build-essential set
# requirements.txt's *-binary packages don't need.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

# Koyeb injects $PORT at runtime (do not hardcode 8000 in the bind address)
# — the shell form is required so $PORT/$WEB_CONCURRENCY actually expand;
# the exec-form JSON array CMD does not perform shell substitution.
# WEB_CONCURRENCY (default 2) is uvicorn's own multi-process worker count,
# not gunicorn — each worker is an independent process with its own
# asyncpg connection pool, no extra process manager needed for this scale.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2}"]
