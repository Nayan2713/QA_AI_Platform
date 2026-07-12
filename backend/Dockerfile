# ==============================================================================
# Django Backend Dockerfile
# ==============================================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOME=/home/django

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browsers + OS deps
RUN playwright install --with-deps chromium

# Create non-root user WITH a real home directory
RUN groupadd -r django && \
    useradd -r -g django -u 1000 -d /home/django -m django

# Create dirs and fix ownership
RUN mkdir -p /app/staticfiles /app/media /app/logs /ms-playwright /home/django && \
    chown -R django:django /app /ms-playwright /home/django

# Copy project
COPY --chown=django:django . /app/

USER django

EXPOSE 8000

CMD ["uvicorn", "qa_engine.asgi:application", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "3"]