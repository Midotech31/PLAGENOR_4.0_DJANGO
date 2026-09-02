import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name, default):
    return os.getenv(name, default).strip().lower() == 'true'


# Secure by default: DEBUG=False unless the operator opts in.
DEBUG = _env_bool('DEBUG', 'False')
PRIVILEGED_MFA_ENFORCEMENT = os.getenv(
    'PRIVILEGED_MFA_ENFORCEMENT', 'false' if DEBUG else 'true'
).lower() == 'true'
CSP_REPORT_ONLY = _env_bool(
    'CSP_REPORT_ONLY',
    'true' if DEBUG else 'false',
)
TRUST_PROXY_HEADERS = _env_bool(
    'TRUST_PROXY_HEADERS',
    'true' if os.getenv('RENDER_EXTERNAL_HOSTNAME') else 'false',
)
RATE_LIMIT_BACKEND = os.getenv(
    'RATE_LIMIT_BACKEND', 'cache' if DEBUG else 'database'
).strip().lower()
if RATE_LIMIT_BACKEND not in {'cache', 'database'}:
    raise ImproperlyConfigured(
        "RATE_LIMIT_BACKEND must be either 'cache' or 'database'."
    )
RATE_LIMIT_FAIL_CLOSED = _env_bool(
    'RATE_LIMIT_FAIL_CLOSED', 'false' if DEBUG else 'true'
)

# SECRET_KEY is required in production. We allow a known-insecure fallback
# only when DEBUG is on, so a misconfigured production deploy fails fast
# instead of silently running on a public secret.
SECRET_KEY = os.getenv('SECRET_KEY', '')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'dev-insecure-key-change-in-production'
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY environment variable must be set when DEBUG is False."
        )

# Privileged-account TOTP seeds are encrypted at rest. Production must fail
# during boot if the stable Fernet key is missing or malformed, instead of
# discovering the problem only when a user attempts MFA enrollment/login.
TOTP_ENCRYPTION_KEY = os.getenv('TOTP_ENCRYPTION_KEY', '').strip()
if not DEBUG:
    if not TOTP_ENCRYPTION_KEY:
        raise ImproperlyConfigured(
            "TOTP_ENCRYPTION_KEY must be set when DEBUG is False."
        )
    try:
        from cryptography.fernet import Fernet
        Fernet(TOTP_ENCRYPTION_KEY.encode('ascii'))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise ImproperlyConfigured(
            "TOTP_ENCRYPTION_KEY must be a valid Fernet key."
        ) from exc

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Hostname injected by the hosting platform (Render / Railway / Koyeb…) so the
# app works on *.onrender.com / *.up.railway.app without editing ALLOWED_HOSTS
# by hand. Railway exposes RAILWAY_PUBLIC_DOMAIN; Render, RENDER_EXTERNAL_HOSTNAME.
for _var in ('RENDER_EXTERNAL_HOSTNAME', 'RAILWAY_PUBLIC_DOMAIN'):
    _platform_host = os.getenv(_var, '').strip()
    if _platform_host and _platform_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_platform_host)

# CSRF trusted origins — REQUIRED for POST requests (login, registration,
# every form) over HTTPS on the production domain(s). Without this Django
# rejects them with 403. Set CSRF_TRUSTED_ORIGINS in the env (comma-separated,
# scheme included) or it is derived from the non-local hosts as https origins.
_csrf_env = os.getenv('CSRF_TRUSTED_ORIGINS', '').strip()
if _csrf_env:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_env.split(',') if o.strip()]
else:
    CSRF_TRUSTED_ORIGINS = [
        f"https://{h.strip()}" for h in ALLOWED_HOSTS
        if h.strip() and h.strip() not in ('localhost', '127.0.0.1')
    ]

INSTALLED_APPS = [
    # django-modeltranslation must be loaded BEFORE django.contrib.admin so
    # the admin sees its registered translation options at class-definition
    # time. See https://django-modeltranslation.readthedocs.io
    'modeltranslation',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_htmx',
    'accounts',
    'core',
    'dashboard',
    'documents',
    'notifications',
]

# ─── django-modeltranslation ─────────────────────────────────────────────
MODELTRANSLATION_DEFAULT_LANGUAGE = 'fr'
MODELTRANSLATION_LANGUAGES = ('fr', 'en', 'ar')
# Fall back through the language chain: requested → fr → en. Never return
# None for a translated field — there is always *some* text to show.
MODELTRANSLATION_FALLBACK_LANGUAGES = ('fr', 'en')
# When writing a translatable field with `obj.name = 'x'`, also populate the
# default-language column and any empty per-language columns. Prevents the
# common "saved a Service, name disappeared in another locale" surprise.
MODELTRANSLATION_AUTO_POPULATE = 'default'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Honour User.preferred_language — must run AFTER AuthenticationMiddleware
    # (needs request.user) and AFTER LocaleMiddleware (which has already
    # activated a language from the cookie / Accept-Language header).
    'dashboard.middleware.PreferredLanguageMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'dashboard.middleware.PrivilegedMFAMiddleware',
    'dashboard.middleware.ContentSecurityPolicyMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'dashboard.middleware.UpdateLastSeenMiddleware',
    'dashboard.middleware.ForcePasswordChangeMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

ROOT_URLCONF = 'plagenor.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                'dashboard.context_processors.notifications',
                'dashboard.context_processors.announcements',
            ],
        },
    },
]

WSGI_APPLICATION = 'plagenor.wsgi.application'

AUTH_USER_MODEL = 'accounts.User'

DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)

# Database configuration
# Production: Set DATABASE_URL environment variable (e.g., postgresql://user:pass@host:5432/dbname)
# Local development: Falls back to SQLite automatically
if os.getenv('DATABASE_URL'):
    # Hosted production databases require TLS. Local PostgreSQL containers
    # used by CI/development may opt out explicitly; the secure default stays
    # enabled everywhere else.
    database_ssl_required = os.getenv(
        'DATABASE_SSL_REQUIRE', 'true'
    ).lower() == 'true'
    DATABASES = {
        'default': dj_database_url.parse(
            os.getenv('DATABASE_URL'),
            conn_max_age=600,
            ssl_require=database_ssl_required,
        )
    }
elif DEBUG:
    # SQLite fallback for local development without PostgreSQL.
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': DATA_DIR / 'plagenor.db',
        }
    }
else:
    # Refuse to run in production on the ephemeral SQLite fallback: on hosts
    # like Render the disk is wiped on every restart/redeploy, so all data
    # (accounts, requests…) would silently vanish. Fail loudly instead, the
    # same way SECRET_KEY does, so the operator sets DATABASE_URL.
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        "DATABASE_URL is not set. Refusing to start on the ephemeral SQLite "
        "fallback in production — data would be lost on every restart. Set "
        "DATABASE_URL to your PostgreSQL (Supabase) connection string, or set "
        "DEBUG=true for local SQLite development."
    )

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 12},
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --- File storage ---------------------------------------------------------
# Static files are always served by WhiteNoise. Uploaded media goes to
# Supabase Storage (S3-compatible) when the SUPABASE_S3_* env vars are set —
# Render's free disk is ephemeral, so without this generated reports and
# uploads vanish on every restart/redeploy. Locally (no env vars) it falls
# back to the filesystem under MEDIA_ROOT. Either way files are served
# *through Django* (see plagenor.storages.SupabaseMediaStorage and the
# media URL routes) so the IBTIKAR citation gate keeps working and the
# bucket can stay private.
_STATICFILES_STORAGE = {
    'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
}

USE_SUPABASE_STORAGE = bool(
    os.getenv('SUPABASE_S3_ENDPOINT')
    and os.getenv('SUPABASE_S3_ACCESS_KEY_ID')
    and os.getenv('SUPABASE_S3_SECRET_ACCESS_KEY')
)
REQUIRE_PERSISTENT_MEDIA_STORAGE = _env_bool(
    'REQUIRE_PERSISTENT_MEDIA_STORAGE', 'false' if DEBUG else 'true')

_storage_keys = (
    'SUPABASE_S3_ENDPOINT', 'SUPABASE_S3_ACCESS_KEY_ID',
    'SUPABASE_S3_SECRET_ACCESS_KEY',
)
_configured_storage_keys = [key for key in _storage_keys if os.getenv(key)]
if _configured_storage_keys and len(_configured_storage_keys) != len(_storage_keys):
    missing = sorted(set(_storage_keys) - set(_configured_storage_keys))
    raise ImproperlyConfigured(
        "Incomplete private-media storage configuration; missing: "
        + ", ".join(missing)
    )
if REQUIRE_PERSISTENT_MEDIA_STORAGE and not USE_SUPABASE_STORAGE:
    raise ImproperlyConfigured(
        "Persistent private-media storage is required in production. Set the "
        "SUPABASE_S3_ENDPOINT, SUPABASE_S3_ACCESS_KEY_ID and "
        "SUPABASE_S3_SECRET_ACCESS_KEY environment variables."
    )

if USE_SUPABASE_STORAGE:
    STORAGES = {
        'default': {'BACKEND': 'plagenor.storages.SupabaseMediaStorage'},
        'staticfiles': _STATICFILES_STORAGE,
    }
    # Supabase Storage S3 endpoint, e.g.
    # https://<project-ref>.supabase.co/storage/v1/s3
    AWS_S3_ENDPOINT_URL = os.getenv('SUPABASE_S3_ENDPOINT')
    AWS_ACCESS_KEY_ID = os.getenv('SUPABASE_S3_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('SUPABASE_S3_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = os.getenv('SUPABASE_S3_BUCKET', 'media')
    # Supabase exposes a single region per project; it must be supplied.
    AWS_S3_REGION_NAME = os.getenv('SUPABASE_S3_REGION', 'eu-central-1')
    # Supabase only supports path-style addressing.
    AWS_S3_ADDRESSING_STYLE = 'path'
    AWS_DEFAULT_ACL = None          # bucket is private; no per-object ACLs
    AWS_QUERYSTRING_AUTH = False    # we never hand out S3 URLs anyway
    AWS_S3_FILE_OVERWRITE = False   # keep distinct uploads from colliding
else:
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': _STATICFILES_STORAGE,
    }

LANGUAGE_CODE = os.getenv('LANGUAGE_CODE', 'fr')
LANGUAGES = [
    ('fr', 'Français'),
    ('en', 'English'),
    ('ar', 'العربية'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']
USE_I18N = True
USE_L10N = True
TIME_ZONE = 'Africa/Algiers'
USE_TZ = True

# Language cookie settings
LANGUAGE_COOKIE_NAME = 'django_language'
LANGUAGE_COOKIE_AGE = 365 * 24 * 60 * 60  # 1 year
LANGUAGE_COOKIE_HTTPONLY = False
LANGUAGE_COOKIE_SAMESITE = 'Lax'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'
PASSWORD_RESET_TIMEOUT = int(os.getenv('PASSWORD_RESET_TIMEOUT', '86400'))

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 3600  # 1 hour

# PLAGENOR-specific settings
IBTIKAR_BUDGET_CAP = float(os.getenv('IBTIKAR_BUDGET_CAP', '200000'))
VAT_RATE = float(os.getenv('VAT_RATE', '0.19'))
INVOICE_PREFIX = os.getenv('INVOICE_PREFIX', 'GENOCLAB-INV')
PLATFORM_VERSION = '4.0.0'
PLATFORM_AUTHOR = 'Prof. Mohamed Merzoug'
PLATFORM_INSTITUTION = 'ESSBO'

# Restoring a live database inside an ordinary web request is deliberately
# disabled by default. Recovery must normally use the documented isolated
# restore drill; an operator may opt in only for a controlled maintenance
# window after accepting the availability and rollback risks.
ALLOW_WEB_DATABASE_RESTORE = _env_bool('ALLOW_WEB_DATABASE_RESTORE', 'False')

# Render generated documents to PDF via LibreOffice headless.
# Requires `libreoffice-writer` + `default-jre-headless` on the host.
# Disable (DOCUMENT_PDF_ENABLED=False) to serve raw DOCX during dev/CI.
DOCUMENT_PDF_ENABLED = os.getenv('DOCUMENT_PDF_ENABLED', 'True').lower() == 'true'

# PDF conversion backend (see documents/pdf_converter.py):
#   'spawn' (default) — one soffice process per call; robust, ~1.5-5s.
#   'uno'             — warm LibreOffice listener per process; ~6x faster,
#                       falls back to 'spawn' automatically on any failure.
DOCUMENT_PDF_BACKEND = os.getenv('DOCUMENT_PDF_BACKEND', 'spawn').lower()

# Email configuration
# Use SMTP backend automatically when SMTP_HOST is configured in .env
_smtp_host = os.getenv('SMTP_HOST') or os.getenv('EMAIL_HOST', '')
REQUIRE_SMTP = _env_bool('REQUIRE_SMTP', 'false' if DEBUG else 'true')
_smtp_backend = 'django.core.mail.backends.smtp.EmailBackend'
_configured_email_backend = os.getenv(
    'EMAIL_BACKEND',
    _smtp_backend if _smtp_host and _smtp_host != 'localhost'
    else 'django.core.mail.backends.console.EmailBackend',
)
if REQUIRE_SMTP:
    _required_smtp = {
        'SMTP_HOST': _smtp_host,
        'SMTP_USER': os.getenv('SMTP_USER') or os.getenv('EMAIL_HOST_USER', ''),
        'SMTP_PASSWORD': (
            os.getenv('SMTP_PASSWORD') or os.getenv('EMAIL_HOST_PASSWORD', '')
        ),
        'SMTP_FROM': (
            os.getenv('SMTP_FROM') or os.getenv('DEFAULT_FROM_EMAIL', '')
        ),
    }
    _missing_smtp = [key for key, value in _required_smtp.items() if not value]
    if _missing_smtp:
        raise ImproperlyConfigured(
            "Production email delivery is required; missing: "
            + ", ".join(_missing_smtp)
        )
    if _configured_email_backend != _smtp_backend:
        raise ImproperlyConfigured(
            "Production email delivery requires Django's SMTP email backend."
        )
EMAIL_BACKEND = _configured_email_backend
EMAIL_HOST = _smtp_host or 'localhost'
EMAIL_PORT = int(os.getenv('SMTP_PORT') or os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.getenv('SMTP_USER') or os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('SMTP_PASSWORD') or os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('SMTP_FROM') or os.getenv('DEFAULT_FROM_EMAIL', 'noreply@plagenor.essbo.dz')

# ─── Production security headers ─────────────────────────────────────────
if not DEBUG:
    SECURE_SSL_REDIRECT = _env_bool('SECURE_SSL_REDIRECT', 'True')
    SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', 'True')
    CSRF_COOKIE_SECURE = _env_bool('CSRF_COOKIE_SECURE', 'True')
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', 'True')
    SECURE_HSTS_PRELOAD = _env_bool('SECURE_HSTS_PRELOAD', 'False')
    # Trust the X-Forwarded-Proto header when terminated by an upstream proxy.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    X_FRAME_OPTIONS = 'DENY'
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SAMESITE = 'Lax'

# ─── Logging ─────────────────────────────────────────────────────────────
# Without an explicit LOGGING dict Django emits only WARNING+ via Python's
# last-resort handler — `plagenor.audit` / `plagenor.workflow` / `plagenor.
# financial` INFO logs would be discarded. Capture them via the console
# (Docker/journald/cloud-platform-friendly).
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'plagenor': {
            'handlers': ['console'],
            'level': os.getenv('LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Error monitoring (Sentry) ───────────────────────────────────────────
# Opt-in and fully no-op unless SENTRY_DSN is set in the environment, so this
# never affects local/dev or any deploy that hasn't configured it. When a DSN
# is present, unhandled exceptions are reported with the Django integration.
SENTRY_DSN = os.getenv('SENTRY_DSN', '').strip()
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=os.getenv('SENTRY_ENVIRONMENT', 'production'),
        traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0')),
        send_default_pii=False,
    )
