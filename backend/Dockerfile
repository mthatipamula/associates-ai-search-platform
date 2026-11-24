# One image for local development and AWS.
#   local (docker compose): INSTALL_DEV=true  (adds pytest)
#   AWS (CI build):         INSTALL_DEV=false
# Models are baked in by default (PRELOAD_MODELS=true): no runtime downloads.
FROM python:3.12-slim

ARG INSTALL_DEV=false
ARG PRELOAD_MODELS=true

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/models \
    DATA_DIR=/data
WORKDIR /srv

COPY backend/requirements.txt backend/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_DEV" = "true" ]; then pip install --no-cache-dir -r requirements-dev.txt; fi

COPY backend/scripts/preload_models.py ./scripts/preload_models.py
RUN mkdir -p /models && if [ "$PRELOAD_MODELS" = "true" ]; then python scripts/preload_models.py; fi

COPY backend/ ./
COPY data/ /data/
COPY eval/ /eval/

# Run as a non-root user.
RUN useradd --uid 10001 --no-create-home appuser && chown -R appuser /models /eval
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=4)" || exit 1
# One worker per container; on AWS, scale out with more ECS tasks.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
