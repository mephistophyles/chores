FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WEB_DIST_PATH=/app/web \
    MIGRATIONS_PATH=/app/migrations

WORKDIR /app

# Dependency layer first so source edits don't invalidate the wheel cache.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

COPY web/ ./web/
COPY migrations/ ./migrations/

EXPOSE 8000

CMD ["uvicorn", "chores.app:app", "--host", "0.0.0.0", "--port", "8000"]
