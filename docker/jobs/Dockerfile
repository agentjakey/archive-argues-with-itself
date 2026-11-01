# The batch jobs image (docs/CLUSTER.md). Two targets from one file:
#   cpu  Python, Tesseract (English and French), fastembed: embed, ocr (tesseract), judge client, compile
#   gpu  the same plus CUDA PyTorch, sentence-transformers and docTR: embed on GPU, ocr (doctr)
# Build from the repository root:
#   docker build -f docker/jobs/Dockerfile --target cpu -t archive-argues-jobs:cpu-1 .
#   docker build -f docker/jobs/Dockerfile --target gpu -t archive-argues-jobs:gpu-1 .
# The image holds code only: no data, no model weights (they download into the pod's scratch
# volume), no secrets (they arrive as environment variables from Kubernetes Secrets by name).

FROM python:3.11.11-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app/src
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-fra ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 10001 jobs && useradd --uid 10001 --gid 10001 --home-dir /scratch/home --no-create-home jobs
WORKDIR /app
COPY docker/jobs/requirements-cpu.txt /app/docker/jobs/requirements-cpu.txt
RUN pip install --no-cache-dir -r docker/jobs/requirements-cpu.txt

FROM base AS cpu
COPY src /app/src
COPY scripts/v2/jobs.py scripts/v2/catalogue.py scripts/v2/registry.py /app/scripts/v2/
COPY config/jobs /app/config/jobs
COPY config/audit.toml /app/config/audit.toml
USER 10001:10001
ENTRYPOINT []
CMD ["python", "scripts/v2/jobs.py", "--help"]

FROM base AS gpu
# docTR reads images through OpenCV, which needs these two system libraries.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY docker/jobs/requirements-gpu.txt /app/docker/jobs/requirements-gpu.txt
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu124 torch==2.5.1 \
 && pip install --no-cache-dir -r docker/jobs/requirements-gpu.txt
COPY src /app/src
COPY scripts/v2/jobs.py scripts/v2/catalogue.py scripts/v2/registry.py /app/scripts/v2/
COPY config/jobs /app/config/jobs
COPY config/audit.toml /app/config/audit.toml
USER 10001:10001
ENTRYPOINT []
CMD ["python", "scripts/v2/jobs.py", "--help"]
