from django.utils import timezone
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
