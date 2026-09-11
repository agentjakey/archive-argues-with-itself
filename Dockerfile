# Read-only serve layer image. Expects the two data files on a mounted volume:
#   $CIVIC_DB_PATH     (default /data/civic.db)
#   $CIVIC_INDEX_PATH  (default /data/index/vectors.db)
# The entrypoint waits for both before starting uvicorn on $PORT. The web app is
# built inside the image (node stage), so the image never depends on a laptop build.

# --- stage 1: web app -------------------------------------------------------
FROM node:20-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- stage 2: api -----------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CIVIC_DB_PATH=/data/civic.db \
    CIVIC_INDEX_PATH=/data/index/vectors.db \
    CIVIC_CACHE_PATH=/data/cache/answers.db \
    FASTEMBED_CACHE_PATH=/opt/fastembed \
    PORT=8080

WORKDIR /app

# Package install (editable, so REPO_ROOT-relative paths in api/app.py resolve to /app).
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install -e .

# Runtime inputs: config, seed questions (for /examples), the built web app.
COPY config ./config
COPY eval/seed_questions.jsonl ./eval/seed_questions.jsonl
COPY --from=web /web/dist ./web/dist
COPY docker/entrypoint.sh /entrypoint.sh

# Bake the query embedding model into the image at build time so the running
# container downloads nothing (N1: its only network call is the configured LLM API).
RUN python -c "import tomllib; from fastembed import TextEmbedding; \
m = tomllib.load(open('config/pilot.toml', 'rb'))['index']['embedding_model']; \
TextEmbedding(model_name=m); print('cached', m)"

RUN chmod +x /entrypoint.sh
EXPOSE 8080
CMD ["/entrypoint.sh"]
