"""Isolated settings for deterministic browser and accessibility tests."""

from .settings import *  # noqa: F401,F403


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATA_DIR / 'plagenor-e2e.sqlite3',  # noqa: F405
    },
}
ROOT_URLCONF = 'plagenor.urls_e2e'
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
PRIVILEGED_MFA_ENFORCEMENT = False
RATE_LIMIT_BACKEND = 'cache'
RATE_LIMIT_FAIL_CLOSED = False
# Each Playwright project uses a distinct documentation-only proxy address so
# the real per-IP login throttle stays enabled without coupling browser suites.
TRUST_PROXY_HEADERS = True
