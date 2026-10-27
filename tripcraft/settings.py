"""
Django settings for TripCraft AI.

All secrets and environment-specific values are read from environment
variables (optionally loaded from a local .env file during development).
See .env.example for the full list.
"""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load a local .env file if present (never committed to Git).
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG", default=False)

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        # Development-only key so the project runs out of the box locally.
        SECRET_KEY = "django-insecure-local-development-only-key-change-me"
    else:
        raise ImproperlyConfigured("SECRET_KEY must be set when DEBUG is False.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# Render exposes the public hostname of the service in this variable.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.humanize",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "planner",
    "support",
]

MIDDLEWARE = [
    "support.middleware.RequestLoggingMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "tripcraft.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "planner.context_processors.site",
                "support.context_processors.assistant",
            ],
        },
    },
]

WSGI_APPLICATION = "tripcraft.wsgi.application"

# SQLite locally; PostgreSQL (or anything else) when DATABASE_URL is set.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = os.environ.get("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "planner:my_trips"
LOGOUT_REDIRECT_URL = "planner:home"

# Keep request bodies small: the app only ever posts short forms and JSON.
DATA_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tripcraft"}}

CSRF_FAILURE_VIEW = "support.views.errors.csrf_failure"

# --- MongoDB (assistant chat logs + feedback only) -------------------------
MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME", "tripcraft")
MONGODB_TIMEOUT_MS = int(os.environ.get("MONGODB_TIMEOUT_MS", "2500"))

# --- Third-party weather API (Open-Meteo) ----------------------------------
WEATHER_TIMEOUT_SECONDS = float(os.environ.get("WEATHER_TIMEOUT_SECONDS", "4"))

# --- Rate limits: scope -> (max requests, window seconds) per client IP ------
RATE_LIMITS = {
    "generate": (int(os.environ.get("RATE_LIMIT_GENERATE", "6")), 600),
    "chat": (int(os.environ.get("RATE_LIMIT_CHAT", "20")), 60),
}
# Render terminates TLS at a proxy that sets X-Forwarded-For.
TRUST_X_FORWARDED_FOR = env_bool("TRUST_X_FORWARDED_FOR", default=bool(RENDER_EXTERNAL_HOSTNAME))

# --- AI provider -----------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
AI_TIMEOUT_SECONDS = int(os.environ.get("AI_TIMEOUT_SECONDS", "60"))
AI_MAX_OUTPUT_TOKENS = int(os.environ.get("AI_MAX_OUTPUT_TOKENS", "16000"))

# --- Production security ---------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"}},
    "loggers": {
        "planner": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO"), "propagate": False},
        "support": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO"), "propagate": False},
        "tripcraft.requests": {"handlers": ["console"], "level": os.environ.get("REQUEST_LOG_LEVEL", "INFO"), "propagate": False},
        # Our middleware already logs every request; silence Django's duplicate 4xx/5xx request warnings.
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
