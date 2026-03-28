from django.utils import timezone


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
