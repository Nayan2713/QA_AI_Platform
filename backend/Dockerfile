# # ==============================================================================
# # Django Backend Dockerfile - Supports Dev and Prod
# # ==============================================================================
# FROM python:3.11-slim AS base

# # Prevent Python from writing .pyc files and buffer stdout/stderr
# ENV PYTHONDONTWRITEBYTECODE=1 \
#     PYTHONUNBUFFERED=1 \
#     PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
#     PORT=8000

# WORKDIR /app

# # Install system dependencies
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     curl \
#     postgresql-client \
#     && rm -rf /var/lib/apt/lists/*

# # Optimize layer caching: Install Python requirements first
# COPY requirements.txt /app/
# RUN pip install --no-cache-dir -r requirements.txt gunicorn


# # Install Playwright system dependencies and Chromium
# RUN python -m playwright install --with-deps chromium && \
#     rm -rf /root/.cache

# # Create a non-root user and group
# RUN groupadd -r django && useradd -r -g django -u 1000 django

# # Create directories for volumes and logs, set permissions
# RUN mkdir -p /app/static /app/media /app/logs /ms-playwright && \
#     chown -R django:django /app /ms-playwright

# # Copy project files
# COPY --chown=django:django . /app/

# # Make entrypoint script executable
# RUN chmod +x /app/entrypoint.sh && \
#     chown django:django /app/entrypoint.sh

# # Use the non-root user
# USER django

# # Expose Django port
# EXPOSE 8000

# # Entrypoint handles waits, migrations, static files
# ENTRYPOINT ["/app/entrypoint.sh"]

# # Default command runs development server (can be overridden in docker-compose for prod)
# CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (Playwright needs these)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browsers + OS deps
RUN playwright install --with-deps chromium

COPY . .

RUN python manage.py collectstatic --noinput || true

EXPOSE 8000
CMD ["gunicorn", "qa_engine.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]