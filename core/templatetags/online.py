from django import template
from django.utils import timezone
from datetime import timedelta

register = template.Library()

@register.filter
def is_online(user):
    """Check if user was active in the last 5 minutes."""
    if hasattr(user, 'last_seen') and user.last_seen:
        return (timezone.now() - user.last_seen) < timedelta(minutes=5)
    return False
