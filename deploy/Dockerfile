# Backend container for the Enterprise Voice Assistant.
#
# Runs the FastAPI app in a slim, non-root image. TLS, CORS, the strict CSP and
# security headers are applied by the reverse proxy (Caddyfile) in front of it,
# which also serves the pre-built SPA from the host's frontend/dist.
FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install pinned dependencies first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Run as an unprivileged user; data lives under /srv/data (pin DATABASE_PATH and
# AUDIO_DIR there in your env, matching the api-data volume).
RUN useradd --create-home appuser && mkdir -p /srv/data && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
