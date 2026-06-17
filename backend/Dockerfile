# syntax=docker/dockerfile:1
FROM python:3.11-slim

# - PYTHONUNBUFFERED: stream logs straight to stdout (no buffering)
# - PYTHONDONTWRITEBYTECODE: no .pyc clutter
# - data dir for the SQLite DB + uploaded audio/images (mount a volume here
#   so they survive container restarts and image rebuilds)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATABASE_PATH=/data/mandarin_stories.db \
    UPLOAD_DIR=/data/uploads

WORKDIR /app

# System libraries the scientific wheels need at runtime.
#   libgomp1   -> OpenMP, required by numpy/scipy (missing on slim -> import crash)
#   libsndfile1 -> audio I/O safety net for parselmouth / soundfile paths
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first so this layer is cached across code changes.
COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt

# Application code.
COPY . .

# Fail the build (not a live request) if any heavy dependency can't import —
# this surfaces missing-library problems here instead of "sometimes at runtime".
# It also warms jieba's prefix dictionary so the first request isn't slow.
RUN python -c "import main; import jieba; jieba.initialize(); print('import + jieba OK')"

# Run as a non-root user and give it ownership of the data directory.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

VOLUME ["/data"]
EXPOSE 8000

# Container-level health check hitting the app's /health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request,sys; url='http://127.0.0.1:'+os.getenv('PORT','8000')+'/health'; sys.exit(0 if urllib.request.urlopen(url, timeout=4).status==200 else 1)"

# ${PORT} lets hosts like Render/Fly inject the port; defaults to 8000 locally.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=*"]
