import os
import warnings
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

warnings.filterwarnings('ignore', message='.*StreamingHttpResponse.*')

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / '.env')
load_dotenv(dotenv_path=BASE_DIR.parent / '.env')

# No insecure fallback — crash loudly at startup if SECRET_KEY is missing
try:
    SECRET_KEY = os.environ['SECRET_KEY']
except KeyError:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        "SECRET_KEY environment variable is not set. Refusing to start with an "
        "insecure default — set SECRET_KEY in the environment/.env before running."
    )


SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Controlled by env var; defaults to False (safe for production)
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# Restrict to real hostnames in production via env var. Only becomes a true
# wildcard if ALLOWED_HOSTS is explicitly set to '*' — an empty/unset var
# falls back to localhost only, and an explicit hostname list is never
# silently widened back to '*'.
_allowed = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1')
if _allowed.strip() == '*':
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = [h.strip() for h in _allowed.split(',') if h.strip()]
import logging.config
from qa_engine.logging_config import configure_logging
configure_logging()

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'debug.log'),
            'maxBytes': 0,  # Disable rotation on Windows to prevent WinError 32 PermissionError
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'error.log'),
            'maxBytes': 0,  # Disable rotation on Windows to prevent WinError 32 PermissionError
            'backupCount': 5,
            'formatter': 'verbose',
            'level': 'ERROR',
        },
    },
    'loggers': {
        'django': {'handlers': ['console', 'file'], 'level': 'INFO'},
        'celery': {'handlers': ['console', 'file'], 'level': 'INFO'},
        'qa_engine': {'handlers': ['console', 'file', 'error_file'], 'level': 'DEBUG'},
    },
}

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'core',
    'accounts',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', 
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'qa_engine.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'qa_engine.wsgi.application'
ASGI_APPLICATION = 'qa_engine.asgi.application'

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#         'OPTIONS': {
#             'timeout': 60,
#         }
#     }
# }


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'qa_ai_platform'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'root'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
        # OPTIMIZED: reuse DB connections across requests instead of
        # opening a new connection every time (saves ~2-5ms per query).
        'CONN_MAX_AGE': 60,
        # FIX: health-check persistent connections before reuse so that
        # connections dropped by Postgres (idle timeout / server restart)
        # are detected and transparently replaced instead of raising
        # OperationalError: "server closed the connection unexpectedly".
        'CONN_HEALTH_CHECKS': True,
    }
}

# NOTE: SQLite PRAGMA signal removed — active DB is Postgres.
# If you switch back to SQLite, re-add the connection_created signal
# with PRAGMA journal_mode=WAL and busy_timeout=60000.

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# FIX: Support reverse proxy SSL detection
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# FIX: enable HTTPS security headers when not in debug mode
if not DEBUG and os.getenv('ENABLE_SSL', 'False') == 'True':
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')  # <--- production only
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}
# FIX: read allowed origins from env so docker-compose and local both work
_cors_origins = os.getenv(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:3000,http://127.0.0.1:3000,http://localhost:81,http://127.0.0.1:81,http://52.144.45.25:81,http://52.144.45.25:8080,https://workvoro.com,https://www.workvoro.com'
)
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins.split(',') if o.strip()]
CORS_ALLOW_CREDENTIALS = True

_csrf_origins = os.getenv(
    'CSRF_TRUSTED_ORIGINS',
    'http://localhost:3000,http://127.0.0.1:3000,http://localhost:81,http://127.0.0.1:81,http://localhost,http://127.0.0.1,http://52.144.45.25:81,http://52.144.45.25:8080,https://workvoro.com,https://www.workvoro.com'
)
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(',') if o.strip()]

# Allow all origins in debug/development mode to prevent CORS issues
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'qa_engine.exception_handler.custom_exception_handler',
    'DEFAULT_RENDERER_CLASSES': (
        'core.renderers.GlobalJSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'QA Engineer MVP — AI Platform API Specification',
    'DESCRIPTION': (
        'Comprehensive OpenAPI 3.0 REST API documentation for QA Engineer MVP.\n\n'
        'This API powers autonomous application crawling, Playwright test generation & execution, '
        'batch runner, self-healing test runs, visual UI defect scanning, real-time telemetry, and bug management.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/',
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': True,
        'defaultModelsExpandDepth': 2,
        'defaultModelExpandDepth': 2,
        'docExpansion': 'list',
        'filter': True,
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': False,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',
}

def _ensure_redis_protocol(url: str) -> str:
    """Guarantee ``protocol=2`` is present in a Redis URL only if redis-py is v5+.

    redis-py 5.x defaults to RESP3 and sends the ``HELLO 3`` command which
    older Redis servers reject.  This helper appends the query param so that
    every connection (Celery broker, result backend, raw clients) stays on
    the safe RESP2 protocol.
    """
    import redis
    try:
        version_parts = [int(p) for p in redis.__version__.split('.') if p.isdigit()]
    except Exception:
        version_parts = []
    
    if version_parts and version_parts[0] >= 5:
        if 'protocol=' in url:
            return url
        return f"{url}?protocol=2" if '?' not in url else f"{url}&protocol=2"
    return url

CELERY_BROKER_URL = _ensure_redis_protocol(
    os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
)
CELERY_RESULT_BACKEND = _ensure_redis_protocol(
    os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
)

import redis
try:
    _redis_version = [int(p) for p in redis.__version__.split('.') if p.isdigit()]
except Exception:
    _redis_version = []

if _redis_version and _redis_version[0] >= 5:
    CELERY_BROKER_TRANSPORT_OPTIONS = {'protocol': 2}
    CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {'protocol': 2}
else:
    CELERY_BROKER_TRANSPORT_OPTIONS = {}
    CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {}
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# OPTIMIZED: expire task results after 1 hour to keep Redis lean
CELERY_TASK_RESULT_EXPIRES = 3600

# OPTIMIZED: route tasks to dedicated queues so discovery/execution/quality
# can be scaled and prioritised independently.
CELERY_TASK_ROUTES = {
    'tasks.discovery.start_discovery':      {'queue': 'discovery'},
    'tasks.execution.execute_test':         {'queue': 'execution'},
    'tasks.execution.run_quality_analysis': {'queue': 'quality'},
    'tasks.quality_check.*':                {'queue': 'quality'},
    'tasks.bug_detection.*':                {'queue': 'quality'},
    'tasks.test_generation.*':              {'queue': 'discovery'},
}

# OPTIMIZED: prevent runaway tasks from piling up on the broker
CELERY_TASK_ANNOTATIONS = {
    'tasks.discovery.start_discovery':      {'rate_limit': '5/m'},
    'tasks.execution.execute_test':         {'rate_limit': '6/m'},
    'tasks.execution.run_quality_analysis': {'rate_limit': '20/m'},
}

# OPTIMIZED: avoid large message payloads being lost silently
CELERY_TASK_SOFT_TIME_LIMIT = 600   # 10 min soft limit: allows task to catch SoftTimeLimitExceeded and cleanly exit browser instances
CELERY_TASK_TIME_LIMIT      = 900   # 15 min hard limit: forcibly kills task process if it runs away / hangs

# OPTIMIZED: track task start states to allow active progress updates on the frontend
CELERY_TASK_TRACK_STARTED = True

# OPTIMIZED: prevent workers from prefetching multiple tasks from the broker.
# Setting it to 1 ensures a worker only grabs one scan at a time, preventing task starvation
# and memory bottlenecks (OOM) caused by a single worker process hoarding multiple browser executions.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

OLLAMA_API_URL = os.getenv('OLLAMA_API_URL', 'http://localhost:11434/api/generate')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen2.5:7b')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', None)


MCP_SERVER_URL = os.getenv('MCP_SERVER_URL', 'http://localhost:5001')

SHODAN_API_KEY = os.getenv('SHODAN_API_KEY', None)
VIRUSTOTAL_API_KEY = os.getenv('VIRUSTOTAL_API_KEY', None)