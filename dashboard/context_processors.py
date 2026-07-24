from notifications.models import Notification


def notifications(request):
    if request.user.is_authenticated:
        unread = Notification.objects.filter(user=request.user, read=False)
        return {
            'unread_count': unread.count(),
            'recent_notifications': unread.order_by('-created_at')[:10],
        }
    return {}


def announcements(request):
    """Active platform announcements targeted at the current user's audience."""
    if not request.user.is_authenticated:
        return {}
    from core.models import Announcement
    active = Announcement.objects.filter(active=True)
    visible = [a for a in active if a.visible_to(request.user)]
    return {'active_announcements': visible}
