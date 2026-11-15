# syntax=docker/dockerfile:1.7
FROM node:24.11.0-bookworm-slim AS frontend-build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/scripts ./scripts
RUN npm ci --ignore-scripts && npm run prepare:vendor

FROM python:3.14.2-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
WORKDIR /app
COPY deploy/requirements-runtime.txt /tmp/requirements-runtime.txt
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
      --index-url https://download.pytorch.org/whl/cpu torch==2.10.0+cpu \
    && python -m pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements-runtime.txt \
    && rm /tmp/requirements-runtime.txt \
    && addgroup --system --gid 10001 vexplorer \
    && adduser --system --uid 10001 --ingroup vexplorer --home /nonexistent --no-create-home vexplorer \
    && mkdir -p /var/lib/vexplorer \
    && chown vexplorer:vexplorer /var/lib/vexplorer
COPY --chown=vexplorer:vexplorer backend/app ./backend/app
COPY --chown=vexplorer:vexplorer tools/__init__.py tools/backup.py ./tools/
COPY --chown=vexplorer:vexplorer frontend/index.html frontend/app.js frontend/styles.css ./frontend/
COPY --chown=vexplorer:vexplorer frontend/explorer.html frontend/explorer.js frontend/explorer.css ./frontend/
COPY --chown=vexplorer:vexplorer frontend/reconstruction.html frontend/reconstruction.js frontend/reconstruction-state.js frontend/reconstruction.css ./frontend/
COPY --chown=vexplorer:vexplorer frontend/assets ./frontend/assets
COPY --chown=vexplorer:vexplorer frontend/api ./frontend/api
COPY --chown=vexplorer:vexplorer frontend/components ./frontend/components
COPY --chown=vexplorer:vexplorer frontend/core ./frontend/core
COPY --from=frontend-build --chown=vexplorer:vexplorer /src/frontend/vendor ./frontend/vendor
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).read()"]
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
