"""Isolated settings for deterministic browser and accessibility tests."""

from .settings import *  # noqa: F401,F403
import os
import re
from django.core.exceptions import ImproperlyConfigured

database_name = os.getenv('PLAGENOR_E2E_DATABASE_NAME', 'plagenor-e2e.sqlite3')
if database_name != 'plagenor-e2e.sqlite3' and not re.fullmatch(r'plagenor-e2e-[A-Za-z0-9]+\.sqlite3', database_name):
    raise ImproperlyConfigured('The browser-test database must use an isolated E2E filename.')


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATA_DIR / database_name,  # noqa: F405
    },
}
ROOT_URLCONF = 'plagenor.urls_e2e'
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
RATE_LIMIT_BACKEND = 'cache'
RATE_LIMIT_FAIL_CLOSED = False
# Each Playwright project uses a distinct documentation-only proxy address so
# the real per-IP login throttle stays enabled without coupling browser suites.
TRUST_PROXY_HEADERS = True
# Exercise the same enforced, no-eval policy as production. Report-only mode
# previously hid runtime failures in Alpine's standard evaluator.
CSP_REPORT_ONLY = False
