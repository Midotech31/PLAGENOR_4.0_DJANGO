from notifications.models import Notification


def notifications(request):
    if request.user.is_authenticated:
        unread = Notification.objects.filter(user=request.user, read=False)
        return {
            'unread_count': unread.count(),
            'recent_notifications': unread.order_by('-created_at')[:10],
        }
    return {}
