from django.conf import settings
from django.utils import timezone, translation
from django.shortcuts import redirect


class UpdateLastSeenMiddleware:
    """Update user's last_seen timestamp on every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            try:
                # Update every 5 minutes max to avoid excessive DB writes
                from accounts.models import User
                User.objects.filter(pk=request.user.pk).update(last_seen=timezone.now())
            except Exception:
                pass
        return response


class PreferredLanguageMiddleware:
    """Honour an authenticated user's ``preferred_language`` over the cookie /
    Accept-Language header.

    Precedence (per the localization blueprint): user setting > cookie >
    Accept-Language. We must run **after** ``AuthenticationMiddleware`` so
    ``request.user`` is populated, and **after** ``LocaleMiddleware`` so we
    overwrite the language Django already activated from the cookie /
    Accept-Language. ``LocaleMiddleware.process_response`` runs in reverse,
    so the ``Content-Language`` response header reflects our override.

    Defensive: a stored value that is no longer in ``settings.LANGUAGES``
    (e.g. a language that was removed) silently falls through to the
    cookie/header choice; we never raise.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Snapshot once at startup — LANGUAGES doesn't change at runtime.
        self._valid_languages = {code for code, _ in settings.LANGUAGES}

    def __call__(self, request):
        try:
            user = getattr(request, 'user', None)
            if user is not None and user.is_authenticated:
                pref = getattr(user, 'preferred_language', '') or ''
                if pref and pref in self._valid_languages:
                    translation.activate(pref)
                    request.LANGUAGE_CODE = pref
        except Exception:
            # A corrupt user row or stale session must never 500 the request.
            pass
        return self.get_response(request)


class ForcePasswordChangeMiddleware:
    """Redirect users who must change their password to the change-password page."""

    EXEMPT_PATHS = [
        '/accounts/force-change-password/',
        '/accounts/logout/',
        '/i18n/',
        '/static/',
        '/media/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and getattr(request.user, 'must_change_password', False)
            and not any(request.path.startswith(p) for p in self.EXEMPT_PATHS)
        ):
            return redirect('/accounts/force-change-password/')
        return self.get_response(request)


class PrivilegedMFAMiddleware:
    """Require TOTP enrollment for every privileged interactive account."""

    PRIVILEGED_ROLES = {'SUPER_ADMIN', 'PLATFORM_ADMIN', 'FINANCE', 'MEMBER'}
    EXEMPT_PATHS = (
        '/accounts/2fa/setup/', '/accounts/2fa/verify/', '/accounts/logout/',
        '/static/', '/healthz', '/readyz',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (settings.PRIVILEGED_MFA_ENFORCEMENT
                and user is not None and user.is_authenticated
                and getattr(user, 'role', '') in self.PRIVILEGED_ROLES
                and not user.totp_enabled
                and not any(request.path.startswith(p) for p in self.EXEMPT_PATHS)):
            return redirect('/accounts/2fa/setup/')
        return self.get_response(request)


class ContentSecurityPolicyMiddleware:
    """Staged CSP. Report-only is the default until inline UI is migrated."""

    POLICY = (
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; "
        "img-src 'self' data: blob:; font-src 'self' data:; "
        "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        header = ('Content-Security-Policy-Report-Only'
                  if settings.CSP_REPORT_ONLY else 'Content-Security-Policy')
        response.setdefault(header, self.POLICY)
        return response
